"""
Test script for character creation
Run this to verify the gemini_service is working
"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

from gemini_service import (
    create_character_with_agent,
    generate_character_attributes,
    create_character_backstory,
    design_character_abilities
)

def test_individual_tools():
    """Test each tool individually"""
    print("\n" + "="*50)
    print("Testing Individual Tools")
    print("="*50)
    
    # Test 1: Attributes
    print("\n1. Testing generate_character_attributes...")
    try:
        attrs = generate_character_attributes("warrior", "intermediate")
        print(f"✓ Success: {attrs}")
    except Exception as e:
        print(f"✗ Failed: {e}")
    
    # Test 2: Backstory
    print("\n2. Testing create_character_backstory...")
    try:
        backstory = create_character_backstory("Aragorn", "ranger", "fantasy")
        print(f"✓ Success: {backstory}")
    except Exception as e:
        print(f"✗ Failed: {e}")
    
    # Test 3: Abilities
    print("\n3. Testing design_character_abilities...")
    try:
        abilities = design_character_abilities("mage", "advanced", 4)
        print(f"✓ Success: {abilities}")
    except Exception as e:
        print(f"✗ Failed: {e}")

def test_character_creation():
    """Test full character creation with agent (function calling)"""
    print("\n" + "="*50)
    print("Testing Full Character Creation with Agent")
    print("="*50)

    test_description = "A brave elven ranger from a mystical forest, skilled with bow and nature magic"

    print(f"\nCreating character: {test_description}")
    print("\nThis will use Gemini agent with function calling...")
    print("This will take ~20-30 seconds...\n")
    
    try:
        character = create_character_with_agent(test_description)
        
        if character:
            print("\n" + "="*50)
            print("✓ CHARACTER CREATED SUCCESSFULLY!")
            print("="*50)
            
            print("\nCharacter Details:")
            print(f"- Description: {character.get('description', 'N/A')}")
            
            if character.get('attributes'):
                attrs = character['attributes'].get('attributes', {})
                print(f"- Attributes: {attrs}")
                print(f"- Total Power: {character['attributes'].get('total_power', 'N/A')}")
            
            if character.get('backstory'):
                print(f"- Origin: {character['backstory'].get('origin', 'N/A')[:80]}...")
            
            if character.get('abilities'):
                abilities = character['abilities'].get('abilities', [])
                print(f"- Abilities: {[a['name'] for a in abilities]}")
            
            if character.get('equipment'):
                eq = character['equipment']
                print(f"- Equipment: {eq.get('weapon', 'N/A')}, {eq.get('armor', 'N/A')}")
            
            if character.get('summary'):
                print(f"\nSummary:\n{character['summary'][:200]}...")
            
            print("\n✓ All tests passed!")
            return True
        else:
            print("\n✗ Character creation returned None")
            return False
            
    except Exception as e:
        print(f"\n✗ Character creation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("AI CHARACTER DESIGNER - TEST SUITE")
    print("="*60)
    
    # Check environment
    print("\nChecking environment...")
    if not os.path.exists('.env'):
        print("✗ Warning: .env file not found!")
        print("  Create .env file with GEMINI_API_KEY")
    else:
        print("✓ .env file exists")
    
    from dotenv import load_dotenv
    load_dotenv()
    
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key or api_key == 'your_api_key_here':
        print("\n✗ ERROR: GEMINI_API_KEY not set in .env file!")
        print("  Please add your API key to .env file")
        return
    else:
        print(f"✓ API key found (length: {len(api_key)})")
    
    # Run tests
    print("\n" + "="*60)
    print("STARTING TESTS")
    print("="*60)
    
    # Test 1: Individual tools
    test_individual_tools()
    
    # Test 2: Full character creation
    input("\n\nPress Enter to test full character creation (will take ~30s)...")
    success = test_character_creation()
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    if success:
        print("\n✓ ALL TESTS PASSED!")
        print("\nThe character creation system is working correctly.")
        print("You can now start the server and use the extension.")
    else:
        print("\n✗ Some tests failed")
        print("\nCheck the error messages above.")
        print("See TROUBLESHOOTING.md for help.")
    print("\n")

if __name__ == "__main__":
    main()
