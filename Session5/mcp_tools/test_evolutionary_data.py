"""
Test script for evolutionary_data.py tools

Demonstrates the usage of the implemented MCP tools for evolutionary data retrieval.
"""

import asyncio
import json
from evolutionary_data import (
    get_evolutionary_lineage,
    get_species_info,
    get_common_ancestor,
    search_extinct_species
)


async def test_evolutionary_lineage():
    """Test the get_evolutionary_lineage function"""
    print("\n" + "="*80)
    print("Testing get_evolutionary_lineage")
    print("="*80)
    
    species_name = "Homo sapiens"
    print(f"\nFetching lineage for: {species_name}")
    
    result = await get_evolutionary_lineage(species_name, max_depth=10)
    print(f"\nResult:")
    print(json.dumps(result, indent=2))


async def test_species_info():
    """Test the get_species_info function"""
    print("\n" + "="*80)
    print("Testing get_species_info")
    print("="*80)
    
    species_name = "Canis lupus"
    print(f"\nFetching species info for: {species_name}")
    
    result = await get_species_info(species_name, detail_level="basic")
    print(f"\nResult:")
    print(json.dumps(result, indent=2))


async def test_common_ancestor():
    """Test the get_common_ancestor function"""
    print("\n" + "="*80)
    print("Testing get_common_ancestor")
    print("="*80)
    
    species_names = ["Homo sapiens", "Pan troglodytes", "Gorilla gorilla"]
    print(f"\nFinding common ancestor for: {', '.join(species_names)}")
    
    result = await get_common_ancestor(species_names)
    print(f"\nResult:")
    print(json.dumps(result, indent=2))


async def test_extinct_species():
    """Test the search_extinct_species function"""
    print("\n" + "="*80)
    print("Testing search_extinct_species")
    print("="*80)
    
    taxon_filter = "Dinosauria"
    time_range = {"min_mya": 66, "max_mya": 250}
    print(f"\nSearching extinct species in {taxon_filter}")
    print(f"Time range: {time_range['min_mya']} - {time_range['max_mya']} million years ago")
    
    result = await search_extinct_species(
        taxon_filter=taxon_filter,
        time_range_mya=time_range,
        limit=5
    )
    print(f"\nResult:")
    print(json.dumps(result, indent=2))


async def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("MCP TOOLS - EVOLUTIONARY DATA TESTS")
    print("="*80)
    
    try:
        # Test each function
        await test_evolutionary_lineage()
        await test_species_info()
        await test_common_ancestor()
        await test_extinct_species()
        
        print("\n" + "="*80)
        print("All tests completed!")
        print("="*80 + "\n")
        
    except Exception as e:
        print(f"\nError during testing: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
