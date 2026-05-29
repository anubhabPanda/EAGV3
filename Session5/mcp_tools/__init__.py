"""
MCP Tools for Evolution Timeline Project

This package contains all MCP tools for evolutionary data retrieval,
temporal/geological information, phylogenetic analysis, visualization data,
educational content, and external data integration.
"""

from .evolutionary_data import (
    get_evolutionary_lineage,
    get_species_info,
    get_common_ancestor,
    search_extinct_species,
)

from .temporal_geological import (
    get_geological_period_info,
    get_species_by_era,
    calculate_divergence_time,
)

from .phylogenetic_taxonomy import (
    get_phylogenetic_tree,
    get_taxonomic_classification,
    compare_species_traits,
)

from .visualization_data import (
    get_fossil_records,
    get_3d_model_reference,
    get_timeline_events,
    get_geographic_distribution,
)

from .educational_content import (
    get_evolutionary_adaptations,
    get_fun_facts,
    generate_comparison,
)

from .external_integration import (
    search_scientific_papers,
    fetch_image_resources,
    validate_taxonomy,
)

from .fetch_url import fetch_url

__all__ = [
    # Evolutionary Data
    "get_evolutionary_lineage",
    "get_species_info",
    "get_common_ancestor",
    "search_extinct_species",
    # Temporal & Geological
    "get_geological_period_info",
    "get_species_by_era",
    "calculate_divergence_time",
    # Phylogenetic & Taxonomy
    "get_phylogenetic_tree",
    "get_taxonomic_classification",
    "compare_species_traits",
    # Visualization Data
    "get_fossil_records",
    "get_3d_model_reference",
    "get_timeline_events",
    "get_geographic_distribution",
    # Educational Content
    "get_evolutionary_adaptations",
    "get_fun_facts",
    "generate_comparison",
    # External Integration
    "search_scientific_papers",
    "fetch_image_resources",
    "validate_taxonomy",
    # Utilities
    "fetch_url",
]
