"""
Temporal & Geological Tools

Tools for geological period information, species by era, and divergence time calculations.
"""

from typing import Dict, List, Optional, Any
import httpx
import re


# API Base URLs
MEDIAWIKI_API_BASE = "https://en.wikipedia.org/w/rest.php/v1"
MEDIAWIKI_ACTION_API = "https://en.wikipedia.org/w/api.php"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
PBDB_API_BASE = "https://paleobiodb.org/data1.2"


# Geological timescale data (fallback if APIs don't provide complete info)
GEOLOGICAL_PERIODS = {
    "Holocene": {"start_mya": 0.0117, "end_mya": 0, "era": "Cenozoic", "eon": "Phanerozoic"},
    "Pleistocene": {"start_mya": 2.58, "end_mya": 0.0117, "era": "Cenozoic", "eon": "Phanerozoic"},
    "Pliocene": {"start_mya": 5.333, "end_mya": 2.58, "era": "Cenozoic", "eon": "Phanerozoic"},
    "Miocene": {"start_mya": 23.03, "end_mya": 5.333, "era": "Cenozoic", "eon": "Phanerozoic"},
    "Oligocene": {"start_mya": 33.9, "end_mya": 23.03, "era": "Cenozoic", "eon": "Phanerozoic"},
    "Eocene": {"start_mya": 56.0, "end_mya": 33.9, "era": "Cenozoic", "eon": "Phanerozoic"},
    "Paleocene": {"start_mya": 66.0, "end_mya": 56.0, "era": "Cenozoic", "eon": "Phanerozoic"},
    "Cretaceous": {"start_mya": 145.0, "end_mya": 66.0, "era": "Mesozoic", "eon": "Phanerozoic"},
    "Jurassic": {"start_mya": 201.3, "end_mya": 145.0, "era": "Mesozoic", "eon": "Phanerozoic"},
    "Triassic": {"start_mya": 251.9, "end_mya": 201.3, "era": "Mesozoic", "eon": "Phanerozoic"},
    "Permian": {"start_mya": 298.9, "end_mya": 251.9, "era": "Paleozoic", "eon": "Phanerozoic"},
    "Carboniferous": {"start_mya": 358.9, "end_mya": 298.9, "era": "Paleozoic", "eon": "Phanerozoic"},
    "Devonian": {"start_mya": 419.2, "end_mya": 358.9, "era": "Paleozoic", "eon": "Phanerozoic"},
    "Silurian": {"start_mya": 443.8, "end_mya": 419.2, "era": "Paleozoic", "eon": "Phanerozoic"},
    "Ordovician": {"start_mya": 485.4, "end_mya": 443.8, "era": "Paleozoic", "eon": "Phanerozoic"},
    "Cambrian": {"start_mya": 541.0, "end_mya": 485.4, "era": "Paleozoic", "eon": "Phanerozoic"},
}


async def get_geological_period_info(
    period_name: str,
) -> Dict[str, Any]:
    """
    Info about a geological period: time bounds, key events, climate.

    Args:
        period_name: e.g. "Jurassic", "Holocene"

    Returns:
        {
            "name": str,
            "start_mya": float,
            "end_mya": float,
            "era": str,
            "eon": str,
            "major_events": [str],
            "climate_summary": str,
            "notable_taxa_examples": [str]
        }

    Primary APIs:
        - Wikipedia (MediaWiki REST/Action API)
        - Wikidata SPARQL
    """
    result = {
        "name": period_name,
        "start_mya": 0.0,
        "end_mya": 0.0,
        "era": "",
        "eon": "",
        "major_events": [],
        "climate_summary": "",
        "notable_taxa_examples": []
    }

    try:
        # Step 1: Get basic timescale data from our lookup table
        period_key = period_name.capitalize()
        if period_key in GEOLOGICAL_PERIODS:
            result["start_mya"] = GEOLOGICAL_PERIODS[period_key]["start_mya"]
            result["end_mya"] = GEOLOGICAL_PERIODS[period_key]["end_mya"]
            result["era"] = GEOLOGICAL_PERIODS[period_key]["era"]
            result["eon"] = GEOLOGICAL_PERIODS[period_key]["eon"]

        # Step 2: Get detailed info from Wikipedia
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Try to fetch Wikipedia page for the geological period
            wiki_url = f"{MEDIAWIKI_API_BASE}/page/{period_name}"
            headers = {
                'User-Agent': 'EvolutionTimeline/1.0 (Educational project)'
            }

            try:
                response = await client.get(wiki_url, headers=headers, follow_redirects=True)

                if response.status_code == 200:
                    page_data = response.json()

                    # Extract summary from source
                    if 'source' in page_data:
                        source_text = page_data['source']

                        # Extract climate/summary information from first few paragraphs
                        paragraphs = []
                        for line in source_text.split('\n'):
                            line = line.strip()
                            # Skip templates, file references, headings
                            if (line and
                                not line.startswith('{{') and
                                not line.startswith('[[File:') and
                                not line.startswith('==') and
                                not line.startswith('|') and
                                len(line) > 50):
                                # Clean up wiki markup
                                cleaned = re.sub(r'\[\[([^\]|]+\|)?([^\]]+)\]\]', r'\2', line)
                                cleaned = re.sub(r"'''([^']+)'''", r'\1', cleaned)
                                cleaned = re.sub(r"''([^']+)''", r'\1', cleaned)
                                if cleaned and len(cleaned) > 50:
                                    paragraphs.append(cleaned)
                                    if len(paragraphs) >= 2:
                                        break

                        if paragraphs:
                            result["climate_summary"] = " ".join(paragraphs[:2])

                        # Try to extract major events from sections
                        major_events = []
                        in_events_section = False
                        for line in source_text.split('\n'):
                            if '== Events ==' in line or '== Major events ==' in line:
                                in_events_section = True
                            elif line.startswith('==') and in_events_section:
                                in_events_section = False
                            elif in_events_section and line.startswith('*'):
                                event = re.sub(r'\[\[([^\]|]+\|)?([^\]]+)\]\]', r'\2', line[1:].strip())
                                if event:
                                    major_events.append(event[:200])  # Limit length

                        if major_events:
                            result["major_events"] = major_events[:5]  # Top 5 events

            except Exception as e:
                # Wikipedia fetch failed, continue with basic data
                pass

        # Step 3: If we have time bounds, query PBDB for notable taxa
        if result["start_mya"] > 0 or result["end_mya"] >= 0:
            async with httpx.AsyncClient(timeout=30.0) as client:
                try:
                    pbdb_url = f"{PBDB_API_BASE}/taxa/list.json"
                    params = {
                        "max_ma": str(result["start_mya"]),
                        "min_ma": str(result["end_mya"]),
                        "limit": "10",
                        "show": "full"
                    }

                    response = await client.get(pbdb_url, params=params, headers=headers)

                    if response.status_code == 200:
                        data = response.json()
                        if "records" in data:
                            taxa_examples = []
                            for record in data["records"][:5]:
                                taxa_name = record.get("taxon_name", "")
                                if taxa_name:
                                    taxa_examples.append(taxa_name)
                            result["notable_taxa_examples"] = taxa_examples

                except Exception as e:
                    # PBDB fetch failed, continue
                    pass

    except Exception as e:
        result["error"] = f"Error retrieving geological period info: {str(e)}"

    return result


async def get_species_by_era(
    period_or_era: str,
    taxon_filter: Optional[str] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    Representative species existing in a given era/period.

    Args:
        period_or_era: Period or era name
        taxon_filter: Optional taxonomic filter
        limit: Max results (default 20)

    Returns:
        {
            "results": [
                {
                    "name": str,
                    "taxon_rank": str,
                    "time_range_mya": {"start": float, "end": float},
                    "example_fossil_sites": [str],
                    "data_sources": [str]
                }
            ]
        }

    Primary APIs:
        - PBDB / Neotoma / EarthLife (time interval filters)
    """
    results = []

    try:
        # Determine time range from period/era name
        period_key = period_or_era.capitalize()
        time_range = None

        # Check if it's a known period
        if period_key in GEOLOGICAL_PERIODS:
            time_range = {
                "max_ma": GEOLOGICAL_PERIODS[period_key]["start_mya"],
                "min_ma": GEOLOGICAL_PERIODS[period_key]["end_mya"]
            }
        else:
            # Try to map era names to time ranges
            era_ranges = {
                "Cenozoic": {"max_ma": 66.0, "min_ma": 0},
                "Mesozoic": {"max_ma": 251.9, "min_ma": 66.0},
                "Paleozoic": {"max_ma": 541.0, "min_ma": 251.9},
                "Quaternary": {"max_ma": 2.58, "min_ma": 0},
                "Neogene": {"max_ma": 23.03, "min_ma": 2.58},
                "Paleogene": {"max_ma": 66.0, "min_ma": 23.03},
            }

            for era_name, era_range in era_ranges.items():
                if era_name.lower() in period_or_era.lower():
                    time_range = era_range
                    break

        if not time_range:
            return {
                "results": [],
                "error": f"Could not determine time range for '{period_or_era}'"
            }

        # Query Paleobiology Database
        async with httpx.AsyncClient(timeout=30.0) as client:
            pbdb_url = f"{PBDB_API_BASE}/occs/taxa.json"

            params = {
                "max_ma": str(time_range["max_ma"]),
                "min_ma": str(time_range["min_ma"]),
                "limit": str(limit),
                "show": "coords,loc,paleoloc"
            }

            # Add taxon filter if provided
            if taxon_filter:
                params["base_name"] = taxon_filter

            headers = {
                'User-Agent': 'EvolutionTimeline/1.0 (Educational project)'
            }

            response = await client.get(pbdb_url, params=params, headers=headers)

            if response.status_code == 200:
                data = response.json()

                # Parse PBDB occurrences
                if "records" in data:
                    # Group by taxon to avoid duplicates
                    taxa_dict = {}

                    for record in data["records"]:
                        taxon_name = record.get("tna", record.get("matched_name", "Unknown"))

                        if taxon_name not in taxa_dict:
                            taxa_dict[taxon_name] = {
                                "name": taxon_name,
                                "taxon_rank": record.get("rnk", "Unknown"),
                                "time_range_mya": {
                                    "start": record.get("eag", time_range["max_ma"]),
                                    "end": record.get("lag", time_range["min_ma"])
                                },
                                "example_fossil_sites": [],
                                "data_sources": ["Paleobiology Database"],
                                "occurrences": 0
                            }

                        # Add fossil site location if available
                        location = record.get("cc", "")  # country code
                        if location and location not in taxa_dict[taxon_name]["example_fossil_sites"]:
                            taxa_dict[taxon_name]["example_fossil_sites"].append(location)

                        taxa_dict[taxon_name]["occurrences"] += 1

                    # Convert to list and sort by occurrence count
                    results = sorted(
                        taxa_dict.values(),
                        key=lambda x: x["occurrences"],
                        reverse=True
                    )

                    # Clean up temporary fields and limit sites
                    for item in results:
                        del item["occurrences"]
                        item["example_fossil_sites"] = item["example_fossil_sites"][:5]

    except Exception as e:
        return {
            "results": [],
            "error": f"Error searching species by era: {str(e)}"
        }

    return {
        "results": results[:limit],
        "total_count": len(results),
        "query_parameters": {
            "period_or_era": period_or_era,
            "taxon_filter": taxon_filter,
            "limit": limit
        }
    }


async def calculate_divergence_time(
    species_a: str,
    species_b: str,
) -> Dict[str, Any]:
    """
    Estimate divergence time between two species.

    Args:
        species_a: First species name
        species_b: Second species name

    Returns:
        {
            "estimated_divergence_mya": float,
            "confidence_notes": str,
            "supporting_studies": [
                {"title": str, "year": int, "source": str, "url": str}
            ]
        }

    Primary APIs:
        - Open Tree of Life (tree metadata)
        - PBDB / EarthLife (earliest fossil records)
        - Literature via search_scientific_papers (arXiv/PubMed)
    """
    result = {
        "species_a": species_a,
        "species_b": species_b,
        "estimated_divergence_mya": None,
        "confidence_notes": "",
        "supporting_studies": [],
        "methods_used": []
    }

    try:
        # Import opentree for MRCA calculation
        from opentree import OT

        # Step 1: Get MRCA (Most Recent Common Ancestor) from Open Tree of Life
        try:
            # Resolve species names
            tnrs_result = OT.tnrs_match([species_a, species_b])

            if tnrs_result and len(tnrs_result) >= 2:
                ott_ids = [match.get('ot:ottId') for match in tnrs_result if 'ot:ottId' in match]

                if len(ott_ids) >= 2:
                    # Get MRCA
                    mrca_result = OT.taxon_mrca(ott_ids=ott_ids)
                    mrca_ott_id = mrca_result.get('ott_id') or mrca_result.get('mrca_ott_id')

                    if mrca_ott_id:
                        result["methods_used"].append("Open Tree of Life MRCA")
                        result["mrca_info"] = {
                            "ott_id": mrca_ott_id,
                            "name": mrca_result.get('mrca_name', ''),
                            "rank": mrca_result.get('mrca_rank', '')
                        }

        except Exception as e:
            result["confidence_notes"] = "Could not calculate MRCA from Open Tree of Life. "

        # Step 2: Try TimeTree API for divergence time estimate
        # TimeTree is a database of divergence times
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                # TimeTree API endpoint
                timetree_url = "http://timetree.org/api/pairwise"

                params = {
                    "taxon_a": species_a,
                    "taxon_b": species_b
                }

                headers = {
                    'User-Agent': 'EvolutionTimeline/1.0 (Educational project)'
                }

                response = await client.get(timetree_url, params=params, headers=headers)

                if response.status_code == 200:
                    data = response.json()

                    # TimeTree returns divergence time in millions of years
                    if "divergence_time" in data:
                        result["estimated_divergence_mya"] = float(data["divergence_time"])
                        result["methods_used"].append("TimeTree Database")

                        # Add confidence information
                        if "confidence_interval" in data:
                            ci = data["confidence_interval"]
                            result["confidence_interval"] = {
                                "lower": ci.get("lower"),
                                "upper": ci.get("upper")
                            }
                            result["confidence_notes"] += f"TimeTree estimate with CI [{ci.get('lower')}-{ci.get('upper')}] MYA. "
                        else:
                            result["confidence_notes"] += "TimeTree estimate without confidence interval. "

                        # Add citation if available
                        if "citations" in data and len(data["citations"]) > 0:
                            for citation in data["citations"][:3]:
                                study = {
                                    "title": citation.get("title", ""),
                                    "year": citation.get("year"),
                                    "source": "TimeTree",
                                    "url": citation.get("url", "")
                                }
                                result["supporting_studies"].append(study)

            except Exception as e:
                # TimeTree failed, try alternative methods
                pass

        # Step 3: Fallback - estimate from PBDB fossil records
        if result["estimated_divergence_mya"] is None:
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    # Get earliest fossil records for both species
                    earliest_a = None
                    earliest_b = None

                    for species in [species_a, species_b]:
                        pbdb_url = f"{PBDB_API_BASE}/occs/list.json"
                        params = {
                            "base_name": species,
                            "show": "time",
                            "limit": "1",
                            "order": "eag"  # Order by earliest age
                        }

                        response = await client.get(pbdb_url, params=params, headers=headers)

                        if response.status_code == 200:
                            data = response.json()
                            if "records" in data and len(data["records"]) > 0:
                                record = data["records"][0]
                                earliest_age = record.get("eag", 0)  # Earliest age in Ma

                                if species == species_a:
                                    earliest_a = earliest_age
                                else:
                                    earliest_b = earliest_age

                    # Use the older of the two as a minimum divergence estimate
                    if earliest_a and earliest_b:
                        result["estimated_divergence_mya"] = max(earliest_a, earliest_b)
                        result["methods_used"].append("PBDB fossil record (minimum estimate)")
                        result["confidence_notes"] += f"Estimated from earliest fossil records. This is a MINIMUM estimate. "

            except Exception as e:
                pass

        # Add general notes if no estimate could be made
        if result["estimated_divergence_mya"] is None:
            result["confidence_notes"] = "Could not estimate divergence time from available sources. Consider checking TimeTree.org or scientific literature manually."
        else:
            # Round to 2 decimal places
            result["estimated_divergence_mya"] = round(result["estimated_divergence_mya"], 2)

    except Exception as e:
        result["error"] = f"Error calculating divergence time: {str(e)}"

    return result
