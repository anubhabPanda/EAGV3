"""
Educational Content Tools

Tools for evolutionary adaptations, fun facts, and comparative narratives.
"""

from typing import Dict, List, Optional, Any


async def get_evolutionary_adaptations(
    species_name: str,
    focus: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Narrative explanation of key adaptations along the lineage of a species.

    Args:
        species_name: Species name
        focus: Optional focus area ("locomotion", "diet", "environment", etc.)

    Returns:
        {
            "adaptation_timeline": [
                {
                    "stage_label": str,
                    "time_range_mya": {"start": float, "end": float},
                    "adaptation_description": str,
                    "evidence_summary": str
                }
            ],
            "sources": [str]
        }

    Primary APIs:
        - Wikipedia/Wikidata (main evolutionary narratives)
        - IUCN / SpeciesFYI (ecology and adaptation notes)
        - Literature via search_scientific_papers (arXiv/PubMed)
    """
    # TODO: Implement adaptation narrative composition from multiple sources
    return {
        "adaptation_timeline": [],
        "sources": [],
        "note": "Implementation pending - requires Wikipedia/IUCN/SpeciesFYI/literature integration"
    }


async def get_fun_facts(
    species_name: str,
    count: int = 3,
) -> Dict[str, Any]:
    """
    Engaging, short facts about a species / ancestor for UI.

    Args:
        species_name: Species name
        count: Number of facts to retrieve (default 3)

    Returns:
        {
            "facts": [
                {"text": str, "source_url": str}
            ]
        }

    Primary APIs:
        - Wikipedia
        - FishWatch, SpeciesFYI, IUCN
        - Internal precomputed list (optional)
    """
    # TODO: Implement fun facts retrieval from Wikipedia/FishWatch/SpeciesFYI/IUCN
    return {
        "facts": [],
        "note": "Implementation pending - requires Wikipedia/FishWatch/SpeciesFYI/IUCN integration"
    }


async def generate_comparison(
    species_a: str,
    species_b: str,
    focus: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Human-readable comparison narrative between related species or ancestor vs descendant.

    Args:
        species_a: First species name
        species_b: Second species name
        focus: Optional focus ("morphology", "ecology", "behavior")

    Returns:
        {
            "summary": str,
            "bullet_points": [str],
            "sources": [str]
        }

    Primary APIs:
        - Composition layer using:
            - get_species_info
            - compare_species_traits
            - get_evolutionary_lineage
            - Wikipedia/literature
    """
    # TODO: Implement comparison narrative composition
    return {
        "summary": "",
        "bullet_points": [],
        "sources": [],
        "note": "Implementation pending - requires composition of multiple tool outputs"
    }
