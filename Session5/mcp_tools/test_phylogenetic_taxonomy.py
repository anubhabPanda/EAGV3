"""
Test script for phylogenetic_taxonomy.py tools

Demonstrates the usage of the implemented MCP tools for phylogenetic and taxonomy data.
"""

import asyncio
import json
from phylogenetic_taxonomy import (
    get_phylogenetic_tree,
    get_taxonomic_classification,
    compare_species_traits
)


async def test_phylogenetic_tree():
    """Test the get_phylogenetic_tree function"""
    print("\n" + "="*80)
    print("Testing get_phylogenetic_tree")
    print("="*80)
    
    root_taxon = "Primates"
    max_depth = 2
    print(f"\nBuilding phylogenetic tree for: {root_taxon}")
    print(f"Max depth: {max_depth}")
    
    result = await get_phylogenetic_tree(root_taxon, max_depth=max_depth)
    
    # Print summary
    print(f"\nResult Summary:")
    print(f"  Root: {result.get('root')}")
    print(f"  Node count: {result.get('node_count', 0)}")
    print(f"  Edge count: {result.get('edge_count', 0)}")
    
    # Print first few nodes
    if 'nodes' in result and len(result['nodes']) > 0:
        print(f"\n  First 5 nodes:")
        for node in result['nodes'][:5]:
            print(f"    - {node['name']} ({node['rank']})")
    
    # Print first few edges
    if 'edges' in result and len(result['edges']) > 0:
        print(f"\n  First 5 edges:")
        for edge in result['edges'][:5]:
            print(f"    - {edge['parent_name']} -> {edge['child_name']}")


async def test_taxonomic_classification():
    """Test the get_taxonomic_classification function"""
    print("\n" + "="*80)
    print("Testing get_taxonomic_classification")
    print("="*80)
    
    species_name = "Panthera leo"
    print(f"\nFetching taxonomic classification for: {species_name}")
    
    result = await get_taxonomic_classification(species_name)
    
    print(f"\nResult:")
    print(f"  Canonical name: {result.get('canonical_name')}")
    
    if 'external_ids' in result:
        print(f"\n  External IDs:")
        for key, value in result['external_ids'].items():
            print(f"    - {key}: {value}")
    
    if 'classification' in result:
        print(f"\n  Classification:")
        for taxon in result['classification']:
            print(f"    - {taxon['rank'].ljust(12)}: {taxon['name']}")


async def test_compare_species_traits():
    """Test the compare_species_traits function"""
    print("\n" + "="*80)
    print("Testing compare_species_traits")
    print("="*80)
    
    species_a = "Canis lupus"
    species_b = "Canis familiaris"
    print(f"\nComparing traits between:")
    print(f"  Species A: {species_a}")
    print(f"  Species B: {species_b}")
    
    result = await compare_species_traits(species_a, species_b)
    
    print(f"\nResult:")
    print(f"  Species A: {result.get('species_a')}")
    print(f"  Species B: {result.get('species_b')}")
    print(f"  Trait count: {result.get('trait_count', 0)}")
    
    if 'traits' in result:
        print(f"\n  Trait Comparison:")
        for trait in result['traits']:
            same_diff = "✓ SAME" if trait['notes'] == "Same" else "✗ DIFFERENT"
            print(f"    {trait['trait_name'].ljust(20)}: {same_diff}")
            print(f"      {species_a}: {trait['species_a_value']}")
            print(f"      {species_b}: {trait['species_b_value']}")


async def test_phylogenetic_tree_small():
    """Test with a smaller tree"""
    print("\n" + "="*80)
    print("Testing get_phylogenetic_tree (small tree)")
    print("="*80)
    
    root_taxon = "Felidae"
    max_depth = 1
    print(f"\nBuilding phylogenetic tree for: {root_taxon}")
    print(f"Max depth: {max_depth}")
    
    result = await get_phylogenetic_tree(root_taxon, max_depth=max_depth)
    print(f"\nResult (full):")
    print(json.dumps(result, indent=2))


async def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("MCP TOOLS - PHYLOGENETIC & TAXONOMY TESTS")
    print("="*80)
    
    try:
        # Test each function
        await test_phylogenetic_tree()
        await test_taxonomic_classification()
        await test_compare_species_traits()
        await test_phylogenetic_tree_small()
        
        print("\n" + "="*80)
        print("All tests completed!")
        print("="*80 + "\n")
        
    except Exception as e:
        print(f"\nError during testing: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
