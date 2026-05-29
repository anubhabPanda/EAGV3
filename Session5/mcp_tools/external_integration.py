"""
External Data Integration Tools

Tools for scientific paper search, image resources, and taxonomy validation.
"""

from typing import Dict, List, Optional, Any


async def search_scientific_papers(
    query: str,
    limit: int = 10,
    source_filter: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Search evolutionary / comparative biology literature.

    Args:
        query: Search query
        limit: Max results (default 10)
        source_filter: "arxiv", "pubmed", or "both" (default both)

    Returns:
        {
            "results": [
                {
                    "title": str,
                    "authors": [str],
                    "year": int,
                    "abstract": str,
                    "doi_or_id": str,
                    "url": str
                }
            ]
        }

    Primary APIs:
        - arXiv API
        - PubMed API
        - CrossRef Metadata Search

    LangChain tools:
        - ArxivAPIWrapper / ArxivQueryRun
        - PubmedQueryRun

    Existing MCP servers:
        - glaforge/arxiv-mcp-server
        - rivaldofwijaya/arxiv-mcp-server
        - dakl/arxiv-mcp, etc.
    """
    # TODO: Implement arXiv/PubMed/CrossRef search (or use LangChain tools)
    return {
        "results": [],
        "note": "Implementation pending - requires arXiv/PubMed/CrossRef API integration or LangChain wrapper"
    }


async def fetch_image_resources(
    species_name: str,
    type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fetch image URLs for species and fossils for the UI.

    Args:
        species_name: Species name
        type: Optional type filter ("photo", "illustration", "fossil")

    Returns:
        {
            "images": [
                {
                    "thumbnail_url": str,
                    "full_url": str,
                    "caption": str,
                    "license": str,
                    "source": str
                }
            ]
        }

    Primary APIs:
        - Wikimedia Commons (via MediaWiki API)
        - FishWatch (species images)
        - IUCN (some images; check license)
        - Other domain-specific APIs
    """
    # TODO: Implement Wikimedia Commons/FishWatch/IUCN image search
    return {
        "images": [],
        "note": "Implementation pending - requires Wikimedia Commons/FishWatch/IUCN API integration"
    }


async def validate_taxonomy(
    name: str,
    kingdom_hint: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Given a name, verify its validity, accepted name, synonyms, and authorities.

    Args:
        name: Taxon name to validate
        kingdom_hint: Optional kingdom hint to narrow search

    Returns:
        {
            "accepted_name": str,
            "is_valid": bool,
            "synonyms": [str],
            "authority": str,
            "classification": dict,
            "source_systems": [str]
        }

    Primary APIs:
        - WoRMS (marine taxa validation)
        - Open Tree TNRS (match names → OTT IDs)
        - SpeciesFYI / laji.fi (broader coverage)
    """
    # TODO: Implement WoRMS/Open Tree TNRS/SpeciesFYI taxonomy validation
    return {
        "accepted_name": name,
        "is_valid": False,
        "synonyms": [],
        "authority": "",
        "classification": {},
        "source_systems": [],
        "note": "Implementation pending - requires WoRMS/Open Tree TNRS/SpeciesFYI integration"
    }
