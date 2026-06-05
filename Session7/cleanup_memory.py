"""
Cleanup script to remove duplicate memories from memory.json
"""
import sys
from pathlib import Path

# Add services to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from services.memory_service import Memory

def main():
    print("Loading memory...")
    memory = Memory()
    
    print(f"Current memory items: {len(memory)}")
    
    # Deduplicate
    removed = memory.deduplicate()
    
    print(f"Final memory items: {len(memory)}")
    print(f"Removed {removed} duplicate(s)")
    
    if removed > 0:
        print("\nMemory has been deduplicated and saved to state/memory.json")

if __name__ == "__main__":
    main()
