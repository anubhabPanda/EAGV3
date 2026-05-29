"""
Test script for temporal_geological.py tools

Demonstrates the usage of the implemented MCP tools for temporal and geological data.
"""

import asyncio
import json
from temporal_geological import (
    get_geological_period_info,
    get_species_by_era,
    calculate_divergence_time
)


async def test_geological_period_info():
    """Test the get_geological_period_info function"""
    print("\n" + "="*80)
    print("Testing get_geological_period_info")
    print("="*80)
    
    period_name = "Jurassic"
    print(f"\nFetching geological info for: {period_name}")
    
    result = await get_geological_period_info(period_name)
    print(f"\nResult:")
    print(json.dumps(result, indent=2))


async def test_species_by_era():
    """Test the get_species_by_era function"""
    print("\n" + "="*80)
    print("Testing get_species_by_era")
    print("="*80)
    
    period = "Cretaceous"
    taxon_filter = "Dinosauria"
    print(f"\nFetching species from {period} period")
    print(f"Filtered by taxon: {taxon_filter}")
    
    result = await get_species_by_era(period, taxon_filter=taxon_filter, limit=10)
    print(f"\nResult:")
    print(json.dumps(result, indent=2))


async def test_divergence_time():
    """Test the calculate_divergence_time function"""
    print("\n" + "="*80)
    print("Testing calculate_divergence_time")
    print("="*80)
    
    species_a = "Homo sapiens"
    species_b = "Pan troglodytes"
    print(f"\nCalculating divergence time between:")
    print(f"  Species A: {species_a}")
    print(f"  Species B: {species_b}")
    
    result = await calculate_divergence_time(species_a, species_b)
    print(f"\nResult:")
    print(json.dumps(result, indent=2))


async def test_geological_period_cenozoic():
    """Test with a different geological period"""
    print("\n" + "="*80)
    print("Testing get_geological_period_info (Cenozoic Era)")
    print("="*80)
    
    period_name = "Paleocene"
    print(f"\nFetching geological info for: {period_name}")
    
    result = await get_geological_period_info(period_name)
    print(f"\nResult:")
    print(json.dumps(result, indent=2))


async def test_species_by_era_mesozoic():
    """Test species search in Mesozoic era"""
    print("\n" + "="*80)
    print("Testing get_species_by_era (Mesozoic)")
    print("="*80)
    
    era = "Mesozoic"
    print(f"\nFetching species from {era} era (no taxon filter)")
    
    result = await get_species_by_era(era, limit=5)
    print(f"\nResult:")
    print(json.dumps(result, indent=2))


async def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("MCP TOOLS - TEMPORAL & GEOLOGICAL TESTS")
    print("="*80)
    
    try:
        # Test each function
        await test_geological_period_info()
        await test_species_by_era()
        await test_divergence_time()
        await test_geological_period_cenozoic()
        await test_species_by_era_mesozoic()
        
        print("\n" + "="*80)
        print("All tests completed!")
        print("="*80 + "\n")
        
    except Exception as e:
        print(f"\nError during testing: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
