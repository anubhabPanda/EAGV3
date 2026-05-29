"""
Phylogenetic & Taxonomy Tools

Tools for phylogenetic trees, taxonomic classification, and species trait comparison.
"""

from typing import Dict, List, Optional, Any
import httpx
from opentree import OT


# API Base URLs
MEDIAWIKI_API_BASE = "https://en.wikipedia.org/w/rest.php/v1"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"


async def get_phylogenetic_tree(
    root_taxon: str,
    max_depth: Optional[int] = None,
    include_extinct: bool = True,
) -> Dict[str, Any]:
    """
    Tree/subtree for visualization.

    Args:
        root_taxon: Root taxon name
        max_depth: Max tree depth
        include_extinct: Include extinct taxa (default True)

    Returns:
        {
            "root": str,
            "nodes": [
                {
                    "id": str,
                    "name": str,
                    "rank": str,
                    "time_range_mya": {"start": float, "end": float},
                    "is_extinct": bool
                }
            ],
            "edges": [{"parent_id": str, "child_id": str}]
        }

    Primary APIs:
        - Open Tree of Life (tree_of_life/subtree, taxonomy APIs)
    """
    nodes = []
    edges = []

    try:
        # Step 1: Resolve root taxon name to OTT ID
        tnrs_result = OT.tnrs_match([root_taxon])

        if not tnrs_result or len(tnrs_result) == 0:
            return {
                "root": root_taxon,
                "nodes": [],
                "edges": [],
                "error": f"Root taxon '{root_taxon}' not found in Open Tree of Life"
            }

        match = tnrs_result[0]
        root_ott_id = match.get('ot:ottId')
        root_name = match.get('ot:ottTaxonName', root_taxon)

        # Step 2: Get taxonomic subtree information
        try:
            # Get taxonomy information for the root
            taxon_info = OT.taxon_info(root_ott_id, include_children=True)

            # Add root node
            root_node = {
                "id": f"ott{root_ott_id}",
                "ott_id": root_ott_id,
                "name": root_name,
                "rank": taxon_info.get('rank', 'Unknown'),
                "time_range_mya": {"start": None, "end": None},
                "is_extinct": False,  # Would need additional data source
                "is_root": True
            }
            nodes.append(root_node)

            # Step 3: Get children taxa (one level or multiple levels)
            if 'children' in taxon_info and taxon_info['children']:
                children_ids = taxon_info['children'][:20]  # Limit to 20 children to avoid overwhelming

                for child_id in children_ids:
                    try:
                        child_info = OT.taxon_info(child_id)

                        child_node = {
                            "id": f"ott{child_id}",
                            "ott_id": child_id,
                            "name": child_info.get('name', f"OTT_{child_id}"),
                            "rank": child_info.get('rank', 'Unknown'),
                            "time_range_mya": {"start": None, "end": None},
                            "is_extinct": False,
                            "is_root": False
                        }
                        nodes.append(child_node)

                        # Add edge from root to child
                        edges.append({
                            "parent_id": f"ott{root_ott_id}",
                            "child_id": f"ott{child_id}",
                            "parent_name": root_name,
                            "child_name": child_node["name"]
                        })

                        # If max_depth > 1, get grandchildren
                        if max_depth and max_depth > 1:
                            if 'children' in child_info and child_info['children']:
                                grandchildren_ids = child_info['children'][:10]  # Limit grandchildren

                                for grandchild_id in grandchildren_ids:
                                    try:
                                        grandchild_info = OT.taxon_info(grandchild_id)

                                        grandchild_node = {
                                            "id": f"ott{grandchild_id}",
                                            "ott_id": grandchild_id,
                                            "name": grandchild_info.get('name', f"OTT_{grandchild_id}"),
                                            "rank": grandchild_info.get('rank', 'Unknown'),
                                            "time_range_mya": {"start": None, "end": None},
                                            "is_extinct": False,
                                            "is_root": False
                                        }

                                        # Check if node already exists
                                        if not any(n['id'] == grandchild_node['id'] for n in nodes):
                                            nodes.append(grandchild_node)

                                        edges.append({
                                            "parent_id": f"ott{child_id}",
                                            "child_id": f"ott{grandchild_id}",
                                            "parent_name": child_node["name"],
                                            "child_name": grandchild_node["name"]
                                        })

                                    except Exception as e:
                                        continue

                    except Exception as e:
                        continue

        except Exception as e:
            return {
                "root": root_taxon,
                "nodes": [root_node] if 'root_node' in locals() else [],
                "edges": [],
                "error": f"Error building tree: {str(e)}"
            }

    except Exception as e:
        return {
            "root": root_taxon,
            "nodes": [],
            "edges": [],
            "error": f"Error retrieving phylogenetic tree: {str(e)}"
        }

    return {
        "root": root_taxon,
        "root_ott_id": root_ott_id,
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "max_depth_reached": max_depth or 2
    }


async def get_taxonomic_classification(
    species_name: str,
) -> Dict[str, Any]:
    """
    Full taxonomic path for a species.

    Args:
        species_name: Species name

    Returns:
        {
            "canonical_name": str,
            "classification": [
                {"rank": str, "name": str, "external_ids": dict}
            ]
        }

    Primary APIs:
        - WoRMS, SpeciesFYI, laji.fi, Naturalis BioPortal
        - Open Tree Taxonomy (OTT IDs)
    """
    result = {
        "canonical_name": species_name,
        "classification": [],
        "external_ids": {}
    }

    try:
        # Step 1: Resolve species name using Open Tree of Life
        tnrs_result = OT.tnrs_match([species_name])

        if not tnrs_result or len(tnrs_result) == 0:
            return {
                "canonical_name": species_name,
                "classification": [],
                "error": f"Species '{species_name}' not found"
            }

        match = tnrs_result[0]
        ott_id = match.get('ot:ottId')
        canonical_name = match.get('ot:ottTaxonName', species_name)
        result['canonical_name'] = canonical_name
        result['external_ids']['ott_id'] = ott_id

        # Step 2: Get full lineage from Open Tree of Life
        taxon_info = OT.taxon_info(ott_id, include_lineage=True)

        if 'lineage' in taxon_info:
            # Build classification from lineage (reverse order: kingdom -> species)
            lineage = taxon_info['lineage']

            for taxon in lineage:
                classification_entry = {
                    "rank": taxon.get('rank', 'Unknown'),
                    "name": taxon.get('name', 'Unknown'),
                    "external_ids": {
                        "ott_id": taxon.get('ot:ottId')
                    }
                }
                result['classification'].append(classification_entry)

            # Add the species itself at the end
            result['classification'].append({
                "rank": taxon_info.get('rank', 'species'),
                "name": canonical_name,
                "external_ids": {
                    "ott_id": ott_id
                }
            })

        # Step 3: Try to get additional IDs from Wikidata
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Query Wikidata SPARQL for the species
                sparql_query = f"""
                SELECT ?item ?ncbi_id ?gbif_id ?itis_id WHERE {{
                  ?item ?label "{canonical_name}"@en .
                  ?item wdt:P31 wd:Q16521 .  # instance of taxon
                  OPTIONAL {{ ?item wdt:P685 ?ncbi_id . }}
                  OPTIONAL {{ ?item wdt:P846 ?gbif_id . }}
                  OPTIONAL {{ ?item wdt:P815 ?itis_id . }}
                }}
                LIMIT 1
                """

                headers = {
                    'User-Agent': 'EvolutionTimeline/1.0 (Educational project)',
                    'Accept': 'application/sparql-results+json'
                }

                params = {
                    'query': sparql_query,
                    'format': 'json'
                }

                response = await client.get(WIKIDATA_SPARQL, params=params, headers=headers)

                if response.status_code == 200:
                    data = response.json()

                    if 'results' in data and 'bindings' in data['results']:
                        bindings = data['results']['bindings']
                        if len(bindings) > 0:
                            binding = bindings[0]

                            if 'ncbi_id' in binding:
                                result['external_ids']['ncbi_taxonomy_id'] = binding['ncbi_id']['value']
                            if 'gbif_id' in binding:
                                result['external_ids']['gbif_id'] = binding['gbif_id']['value']
                            if 'itis_id' in binding:
                                result['external_ids']['itis_id'] = binding['itis_id']['value']
                            if 'item' in binding:
                                wikidata_id = binding['item']['value'].split('/')[-1]
                                result['external_ids']['wikidata_id'] = wikidata_id

        except Exception as e:
            # Wikidata lookup failed, continue with OTT data
            pass

    except Exception as e:
        result['error'] = f"Error retrieving taxonomic classification: {str(e)}"

    return result


async def compare_species_traits(
    species_a: str,
    species_b: str,
    trait_keys: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Comparative trait table for two species.

    Args:
        species_a: First species name
        species_b: Second species name
        trait_keys: Optional list of specific traits to compare

    Returns:
        {
            "traits": [
                {
                    "trait_name": str,
                    "species_a_value": str,
                    "species_b_value": str,
                    "notes": str,
                    "sources": [str]
                }
            ]
        }

    Primary APIs:
        - SpeciesFYI
        - FishWatch
        - IUCN narratives
        - Wikipedia/Wikidata
    """
    traits = []

    try:
        # Step 1: Get basic taxonomy for both species
        species_a_data = {}
        species_b_data = {}

        # Resolve both species
        tnrs_result = OT.tnrs_match([species_a, species_b])

        if tnrs_result and len(tnrs_result) >= 2:
            # Get data for species A
            match_a = tnrs_result[0]
            ott_id_a = match_a.get('ot:ottId')
            species_a_data['canonical_name'] = match_a.get('ot:ottTaxonName', species_a)
            species_a_data['rank'] = match_a.get('ot:rank', 'Unknown')

            # Get data for species B
            match_b = tnrs_result[1]
            ott_id_b = match_b.get('ot:ottId')
            species_b_data['canonical_name'] = match_b.get('ot:ottTaxonName', species_b)
            species_b_data['rank'] = match_b.get('ot:rank', 'Unknown')

            # Get full taxonomy for both
            try:
                taxon_a = OT.taxon_info(ott_id_a, include_lineage=True)
                taxon_b = OT.taxon_info(ott_id_b, include_lineage=True)

                # Build classification dictionaries
                classification_a = {}
                classification_b = {}

                if 'lineage' in taxon_a:
                    for taxon in taxon_a['lineage']:
                        rank = taxon.get('rank', '').lower()
                        name = taxon.get('name', '')
                        if rank and name:
                            classification_a[rank] = name

                if 'lineage' in taxon_b:
                    for taxon in taxon_b['lineage']:
                        rank = taxon.get('rank', '').lower()
                        name = taxon.get('name', '')
                        if rank and name:
                            classification_b[rank] = name

                species_a_data['classification'] = classification_a
                species_b_data['classification'] = classification_b

            except Exception as e:
                pass

        # Step 2: Compare taxonomic traits
        taxonomic_ranks = ['kingdom', 'phylum', 'class', 'order', 'family', 'genus', 'species']

        for rank in taxonomic_ranks:
            if trait_keys and rank not in trait_keys:
                continue

            value_a = species_a_data.get('classification', {}).get(rank, 'Unknown')
            value_b = species_b_data.get('classification', {}).get(rank, 'Unknown')

            same = value_a == value_b and value_a != 'Unknown'

            trait = {
                "trait_name": rank.capitalize(),
                "species_a_value": value_a,
                "species_b_value": value_b,
                "notes": "Same" if same else "Different",
                "sources": ["Open Tree of Life"]
            }
            traits.append(trait)

        # Step 3: Try to get additional traits from Wikipedia/Wikidata
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Get Wikipedia infobox data via Wikidata for both species
            for species_name, species_data, is_a in [
                (species_a, species_a_data, True),
                (species_b, species_b_data, False)
            ]:
                try:
                    canonical = species_data.get('canonical_name', species_name)

                    # Try to get Wikipedia page
                    wiki_url = f"{MEDIAWIKI_API_BASE}/page/{canonical}"
                    headers = {
                        'User-Agent': 'EvolutionTimeline/1.0 (Educational project)'
                    }

                    response = await client.get(wiki_url, headers=headers, follow_redirects=True)

                    if response.status_code == 200:
                        page_data = response.json()

                        # Extract simple traits from source (basic parsing)
                        if 'source' in page_data:
                            source_text = page_data['source']

                            # Look for conservation status in infobox
                            import re
                            conservation_match = re.search(r'\|\s*status\s*=\s*(\w+)', source_text, re.IGNORECASE)
                            if conservation_match:
                                status = conservation_match.group(1)
                                if is_a:
                                    species_a_data['conservation_status'] = status
                                else:
                                    species_b_data['conservation_status'] = status

                except Exception as e:
                    continue

        # Add conservation status trait if available
        if 'conservation_status' in species_a_data or 'conservation_status' in species_b_data:
            if not trait_keys or 'conservation_status' in trait_keys:
                trait = {
                    "trait_name": "Conservation Status",
                    "species_a_value": species_a_data.get('conservation_status', 'Unknown'),
                    "species_b_value": species_b_data.get('conservation_status', 'Unknown'),
                    "notes": "IUCN Red List status",
                    "sources": ["Wikipedia"]
                }
                traits.append(trait)

    except Exception as e:
        return {
            "species_a": species_a,
            "species_b": species_b,
            "traits": [],
            "error": f"Error comparing species traits: {str(e)}"
        }

    return {
        "species_a": species_a_data.get('canonical_name', species_a),
        "species_b": species_b_data.get('canonical_name', species_b),
        "traits": traits,
        "trait_count": len(traits)
    }
