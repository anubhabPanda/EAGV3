"""
Evolutionary Data Retrieval Tools

Tools for retrieving evolutionary lineages, species information,
common ancestors, and extinct species searches.
"""

from typing import Dict, List, Optional, Any
import httpx
from opentree import OT


# MediaWiki REST API base URL
MEDIAWIKI_API_BASE = "https://en.wikipedia.org/w/rest.php/v1"


async def get_evolutionary_lineage(
    species_name: str,
    max_depth: Optional[int] = None,
    include_extinct: bool = True,
    preferred_sources: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Return the evolutionary lineage of a present-day animal back through major ancestors.

    Args:
        species_name: Common or scientific name
        max_depth: Max number of lineage nodes
        include_extinct: Whether to include extinct taxa
        preferred_sources: e.g. ["opentree", "wikidata"]

    Returns:
        {
            "species": {"name": str, "rank": str, "ids": dict},
            "lineage": [
                {
                    "name": str,
                    "rank": str,
                    "time_range": {"start_mya": float, "end_mya": float, "period": str},
                    "is_extinct": bool,
                    "sources": [{"source": str, "id": str, "url": str}]
                }
            ]
        }

    Primary APIs:
        - Open Tree of Life Web APIs (/tnrs/match_names, /taxonomy/mrca, /taxonomy/subtree)
        - Wikidata SPARQL endpoint
        - Wikipedia / Wikimedia REST
    """
    try:
        # Step 1: Resolve species name using Open Tree of Life TNRS
        tnrs_result = OT.tnrs_match([species_name])

        if not tnrs_result or len(tnrs_result) == 0:
            return {
                "species": {"name": species_name, "rank": "species", "ids": {}},
                "lineage": [],
                "error": f"Species '{species_name}' not found in Open Tree of Life"
            }

        # Get the first (best) match
        match = tnrs_result[0]
        ott_id = match.get('ot:ottId')
        matched_name = match.get('ot:ottTaxonName', species_name)

        # Step 2: Get taxonomic lineage
        lineage_data = []
        try:
            # Get taxonomy information
            taxon_info = OT.taxon_info(ott_id, include_lineage=True)

            if 'lineage' in taxon_info:
                lineage_items = taxon_info['lineage']

                # Apply max_depth if specified
                if max_depth and len(lineage_items) > max_depth:
                    lineage_items = lineage_items[:max_depth]

                for taxon in lineage_items:
                    lineage_entry = {
                        "name": taxon.get('name', 'Unknown'),
                        "rank": taxon.get('rank', 'Unknown'),
                        "ott_id": taxon.get('ot:ottId'),
                        "time_range": {
                            "start_mya": None,
                            "end_mya": None,
                            "period": None
                        },
                        "is_extinct": False,  # Would need additional data source
                        "sources": [{
                            "source": "Open Tree of Life",
                            "id": str(taxon.get('ot:ottId')),
                            "url": f"https://tree.opentreeoflife.org/taxonomy/browse?id={taxon.get('ot:ottId')}"
                        }]
                    }
                    lineage_data.append(lineage_entry)

        except Exception as e:
            # If lineage fetch fails, continue with basic info
            pass

        return {
            "species": {
                "name": matched_name,
                "rank": match.get('ot:rank', 'species'),
                "ids": {
                    "ott_id": ott_id,
                }
            },
            "lineage": lineage_data
        }

    except Exception as e:
        return {
            "species": {"name": species_name, "rank": "species", "ids": {}},
            "lineage": [],
            "error": f"Error retrieving lineage: {str(e)}"
        }


async def get_species_info(
    species_name: str,
    language: str = "en",
    detail_level: str = "basic",
) -> Dict[str, Any]:
    """
    Unified species profile: taxonomy, conservation status, summary, habitats.

    Args:
        species_name: Common or scientific name
        language: Language code (default "en")
        detail_level: "basic" or "full"

    Returns:
        {
            "canonical_name": str,
            "scientific_name": str,
            "common_names": [str],
            "taxonomic_classification": {"kingdom": str, ...},
            "iucn_status": str,
            "short_summary": str,
            "habitats": [str],
            "biomes": [str],
            "distribution_regions": [str],
            "external_links": {"wikipedia": str, "wikidata": str, "iucn": str}
        }

    Primary APIs:
        - IUCN Red List API
        - WoRMS
        - SpeciesFYI
        - laji.fi Taxonomy API
        - Naturalis BioPortal
        - Wikipedia / Wikidata
    """
    result = {
        "canonical_name": species_name,
        "scientific_name": species_name,
        "common_names": [],
        "taxonomic_classification": {},
        "iucn_status": None,
        "short_summary": "",
        "habitats": [],
        "biomes": [],
        "distribution_regions": [],
        "external_links": {}
    }

    try:
        # Step 1: Get Open Tree of Life taxonomy information
        tnrs_result = OT.tnrs_match([species_name])

        if tnrs_result and len(tnrs_result) > 0:
            match = tnrs_result[0]
            ott_id = match.get('ot:ottId')
            result['scientific_name'] = match.get('ot:ottTaxonName', species_name)
            result['canonical_name'] = match.get('unique_name', species_name)

            # Get full taxonomy
            try:
                taxon_info = OT.taxon_info(ott_id, include_lineage=True)

                # Build taxonomic classification from lineage
                if 'lineage' in taxon_info:
                    for taxon in taxon_info['lineage']:
                        rank = taxon.get('rank', '').lower()
                        name = taxon.get('name', '')
                        if rank and name:
                            result['taxonomic_classification'][rank] = name

                # Add current taxon rank
                if 'rank' in taxon_info:
                    result['taxonomic_classification'][taxon_info['rank'].lower()] = result['scientific_name']

            except Exception as e:
                pass

            result['external_links']['opentree'] = f"https://tree.opentreeoflife.org/taxonomy/browse?id={ott_id}"

        # Step 2: Get Wikipedia summary using MediaWiki REST API
        async with httpx.AsyncClient() as client:
            # Try to get Wikipedia page by scientific name
            search_name = result['scientific_name']

            try:
                # Get page with summary
                wiki_url = f"{MEDIAWIKI_API_BASE}/page/{search_name}"
                headers = {
                    'User-Agent': 'EvolutionTimeline/1.0 (Educational project)'
                }

                response = await client.get(wiki_url, headers=headers, follow_redirects=True)

                if response.status_code == 200:
                    page_data = response.json()

                    # Extract summary from source content
                    if 'source' in page_data:
                        # Get first paragraph as summary (basic extraction)
                        source_text = page_data['source']
                        # Remove templates and get first meaningful paragraph
                        lines = source_text.split('\n')
                        for line in lines:
                            if line and not line.startswith('{{') and not line.startswith('[[File:') and len(line) > 50:
                                result['short_summary'] = line.strip()
                                break

                    # Store Wikipedia link
                    if 'title' in page_data:
                        result['external_links']['wikipedia'] = f"https://en.wikipedia.org/wiki/{page_data['title'].replace(' ', '_')}"

            except Exception as e:
                # Wikipedia lookup failed, continue with other sources
                pass

        # For detail_level == "full", could add more API calls here:
        # - IUCN Red List API for conservation status
        # - Additional habitat/distribution data

    except Exception as e:
        result['error'] = f"Error retrieving species info: {str(e)}"

    return result


async def get_common_ancestor(
    species_names: List[str],
) -> Dict[str, Any]:
    """
    Compute most recent common ancestor (MRCA) across ≥2 species.

    Args:
        species_names: Array of species names (length ≥ 2)

    Returns:
        {
            "mrca_name": str,
            "mrca_rank": str,
            "mrca_ott_id": str,
            "supporting_sources": [str],
            "notes": str
        }

    Primary APIs:
        - Open Tree of Life (/taxonomy/mrca or /tree_of_life/mrca)
    """
    if not species_names or len(species_names) < 2:
        return {
            "mrca_name": "",
            "mrca_rank": "",
            "mrca_ott_id": None,
            "supporting_sources": [],
            "error": "At least 2 species names required"
        }

    try:
        # Step 1: Resolve all species names to OTT IDs
        tnrs_result = OT.tnrs_match(species_names)

        if not tnrs_result or len(tnrs_result) < 2:
            return {
                "mrca_name": "",
                "mrca_rank": "",
                "mrca_ott_id": None,
                "supporting_sources": [],
                "error": "Could not resolve species names to taxonomy IDs"
            }

        # Extract OTT IDs from matched results
        ott_ids = [match.get('ot:ottId') for match in tnrs_result if 'ot:ottId' in match]

        if len(ott_ids) < 2:
            return {
                "mrca_name": "",
                "mrca_rank": "",
                "mrca_ott_id": None,
                "supporting_sources": [],
                "error": f"Only {len(ott_ids)} species successfully resolved"
            }

        # Step 2: Get MRCA using Open Tree of Life taxonomy MRCA
        try:
            mrca_result = OT.taxon_mrca(ott_ids=ott_ids)

            mrca_ott_id = mrca_result.get('ott_id') or mrca_result.get('mrca_ott_id')
            mrca_name = mrca_result.get('mrca_name', '')
            mrca_rank = mrca_result.get('mrca_rank', '')

            # Get more info about the MRCA taxon
            if mrca_ott_id:
                try:
                    mrca_info = OT.taxon_info(mrca_ott_id)
                    mrca_name = mrca_info.get('name', mrca_name)
                    mrca_rank = mrca_info.get('rank', mrca_rank)
                except:
                    pass

            return {
                "mrca_name": mrca_name,
                "mrca_rank": mrca_rank,
                "mrca_ott_id": mrca_ott_id,
                "supporting_sources": ["Open Tree of Life"],
                "input_species": [match.get('ot:ottTaxonName', '') for match in tnrs_result],
                "mrca_url": f"https://tree.opentreeoflife.org/taxonomy/browse?id={mrca_ott_id}" if mrca_ott_id else None
            }

        except Exception as e:
            return {
                "mrca_name": "",
                "mrca_rank": "",
                "mrca_ott_id": None,
                "supporting_sources": [],
                "error": f"MRCA calculation failed: {str(e)}"
            }

    except Exception as e:
        return {
            "mrca_name": "",
            "mrca_rank": "",
            "mrca_ott_id": None,
            "supporting_sources": [],
            "error": f"Error in MRCA computation: {str(e)}"
        }


async def search_extinct_species(
    query: Optional[str] = None,
    time_range_mya: Optional[Dict[str, float]] = None,
    taxon_filter: Optional[str] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    Search extinct species by time period, region, and taxon.

    Args:
        query: Free text filter
        time_range_mya: {"min_mya": float, "max_mya": float}
        taxon_filter: e.g. "Cetacea", "Theropoda"
        limit: Max results (default 20)

    Returns:
        {
            "results": [
                {
                    "name": str,
                    "rank": str,
                    "time_range_mya": {"start": float, "end": float},
                    "location_info": str,
                    "data_sources": [str]
                }
            ]
        }

    Primary APIs:
        - Paleobiology Database (PBDB)
        - Neotoma Paleoecology Database
        - EarthLife Consortium REST API
    """
    # Paleobiology Database API endpoint
    PBDB_API_BASE = "https://paleobiodb.org/data1.2"

    results = []

    try:
        async with httpx.AsyncClient() as client:
            # Build PBDB API query parameters
            params = {
                "show": "full",  # Get full taxonomy information
                "limit": str(limit)
            }

            # Add taxon filter
            if taxon_filter:
                params["base_name"] = taxon_filter
            elif query:
                params["taxon_name"] = query

            # Add time range filter
            if time_range_mya:
                # PBDB uses max_ma and min_ma (million years ago)
                if "min_mya" in time_range_mya:
                    params["min_ma"] = str(time_range_mya["min_mya"])
                if "max_mya" in time_range_mya:
                    params["max_ma"] = str(time_range_mya["max_mya"])

            # Query PBDB taxa endpoint
            url = f"{PBDB_API_BASE}/taxa/list.json"
            headers = {
                'User-Agent': 'EvolutionTimeline/1.0 (Educational project)'
            }

            response = await client.get(url, params=params, headers=headers)

            if response.status_code == 200:
                data = response.json()

                # Parse PBDB response
                if "records" in data:
                    for record in data["records"]:
                        # Extract taxon information
                        result_entry = {
                            "name": record.get("taxon_name", "Unknown"),
                            "rank": record.get("taxon_rank", "Unknown"),
                            "time_range_mya": {
                                "start": record.get("firstapp_max_ma"),
                                "end": record.get("lastapp_min_ma")
                            },
                            "location_info": "",  # PBDB has occurrence data, could be enhanced
                            "data_sources": ["Paleobiology Database"],
                            "pbdb_id": record.get("oid"),
                            "extinction_status": "extinct" if record.get("is_extant") == "0" else "extant"
                        }

                        # Only include extinct species if we can confirm
                        if result_entry["extinction_status"] == "extinct":
                            results.append(result_entry)

    except Exception as e:
        return {
            "results": [],
            "error": f"Error searching extinct species: {str(e)}"
        }

    return {
        "results": results,
        "total_count": len(results),
        "query_parameters": {
            "query": query,
            "time_range_mya": time_range_mya,
            "taxon_filter": taxon_filter,
            "limit": limit
        }
    }
