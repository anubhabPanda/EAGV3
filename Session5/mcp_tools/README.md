# MCP Tools for Evolution Timeline Project

This directory contains all 18 MCP tools for the Evolution Timeline web application, organized by category according to `mcp_plan.md`.

## Tool Categories

### 1. Evolutionary Data Retrieval (`evolutionary_data.py`)
- `get_evolutionary_lineage` - Return evolutionary lineage from present-day animal to ancestors
- `get_species_info` - Unified species profile with taxonomy, conservation, habitats
- `get_common_ancestor` - Compute MRCA across 2+ species
- `search_extinct_species` - Search extinct species by time/region/taxon

### 2. Temporal & Geological (`temporal_geological.py`)
- `get_geological_period_info` - Info about geological periods
- `get_species_by_era` - Representative species in a given era/period
- `calculate_divergence_time` - Estimate divergence time between species

### 3. Phylogenetic & Taxonomy (`phylogenetic_taxonomy.py`)
- `get_phylogenetic_tree` - Tree/subtree for visualization
- `get_taxonomic_classification` - Full taxonomic path for species
- `compare_species_traits` - Comparative trait table for two species

### 4. Visualization Data (`visualization_data.py`)
- `get_fossil_records` - Fossil occurrence records (time + geography)
- `get_3d_model_reference` - References to 3D models for taxa
- `get_timeline_events` - Evolutionary/extinction events for lineage
- `get_geographic_distribution` - Historic + modern species range

### 5. Educational Content (`educational_content.py`)
- `get_evolutionary_adaptations` - Narrative of key adaptations
- `get_fun_facts` - Engaging facts about species
- `generate_comparison` - Comparison narrative between species

### 6. External Integration (`external_integration.py`)
- `search_scientific_papers` - Search arXiv/PubMed/CrossRef literature
- `fetch_image_resources` - Fetch images from Wikimedia Commons/FishWatch/IUCN
- `validate_taxonomy` - Validate taxon names via WoRMS/Open Tree/SpeciesFYI

### 7. Utilities (`fetch_url.py`)
- `fetch_url` - Fetch clean markdown from URLs using crawl4ai (headless Chromium)

## Implementation Status

**19 tools total** - 18 domain-specific tools + 1 utility tool.

### Fully Implemented Tools:

**Utilities:**
- ✅ **fetch_url** (`fetch_url.py`) - Clean markdown extraction using crawl4ai

**Evolutionary Data (`evolutionary_data.py`):**
- ✅ **get_evolutionary_lineage** - Uses Open Tree of Life TNRS and taxonomy APIs
- ✅ **get_species_info** - Uses Open Tree of Life + MediaWiki REST API
- ✅ **get_common_ancestor** - Uses Open Tree of Life MRCA calculation
- ✅ **search_extinct_species** - Uses Paleobiology Database API

**Temporal & Geological (`temporal_geological.py`):**
- ✅ **get_geological_period_info** - Uses Wikipedia API + built-in geological timescale + PBDB
- ✅ **get_species_by_era** - Uses Paleobiology Database with time-based filtering
- ✅ **calculate_divergence_time** - Uses Open Tree of Life + TimeTree API + PBDB fallback

**Phylogenetic & Taxonomy (`phylogenetic_taxonomy.py`):**
- ✅ **get_phylogenetic_tree** - Uses Open Tree of Life to build taxonomic trees
- ✅ **get_taxonomic_classification** - Uses Open Tree of Life + Wikidata SPARQL for complete classification
- ✅ **compare_species_traits** - Uses Open Tree of Life + Wikipedia for taxonomic and trait comparison

### Stub Tools:
Most other tools are currently **stubs** with placeholder implementations. Each tool includes:
- Complete function signature with type hints
- Comprehensive docstring with Args/Returns/APIs
- TODO comment indicating required API integrations
- Placeholder return value with implementation note

## Implementation Progress

**11 of 19 tools completed** (58% complete)

### Completed Categories:
1. ✅ **Utilities** - 1/1 tools (100%)
2. ✅ **Evolutionary Data** - 4/4 tools (100%)
3. ✅ **Temporal & Geological** - 3/3 tools (100%)
4. ✅ **Phylogenetic & Taxonomy** - 3/3 tools (100%)

### Remaining Categories:
5. ⏳ **Visualization Data** - 0/4 tools (0%)
6. ⏳ **Educational Content** - 0/3 tools (0%)
7. ⏳ **External Integration** - 0/3 tools (0%)

## Next Steps

1. **Continue Implementation**:
   - Phylogenetic & Taxonomy tools (3 tools)
   - Visualization Data tools (4 tools)
   - Educational Content tools (3 tools)
   - External Integration tools (3 tools)

2. **Testing**: Run existing test scripts
   - `test_evolutionary_data.py`
   - `test_temporal_geological.py`

3. **Error Handling**: Add robust error handling and retry logic

4. **Caching**: Implement caching layer to reduce API calls

5. **Rate Limiting**: Add rate limiting for external APIs

6. **MCP Server**: Create MCP server wrapper with streamable HTTP transport

## Usage

```python
from mcp_tools import get_evolutionary_lineage, get_species_info, fetch_url

# Get evolutionary lineage
lineage = await get_evolutionary_lineage("Whale", max_depth=10)

# Get species information
info = await get_species_info("Homo sapiens", detail_level="full")

# Fetch URL content (fully implemented)
result = await fetch_url("https://en.wikipedia.org/wiki/Evolution")
print(result["text"])  # Clean markdown content
```

## API Keys Required

The following external APIs may require API keys:
- IUCN Red List API
- Some Wikipedia/Wikimedia services (high volume)
- Potentially others depending on usage limits

Store API keys in environment variables or secure configuration.
