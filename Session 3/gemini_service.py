"""
Gemini Agent Service for Character Designer
Uses function calling and tool orchestration for character creation
"""

from google import genai
from google.genai import types
import os
import json
from dotenv import load_dotenv
import base64
from PIL import Image
import io

# Load environment variables
load_dotenv()

# Initialize Gemini client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = "gemini-3-flash-preview" #"gemini-3.1-flash-lite-preview"
IMAGE_MODEL = "gemini-2.5-flash-image"




# Define character design tools
TOOLS = [
    types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="generate_character_attributes",
                description="Generate core character attributes like strength, intelligence, agility, charisma, etc.",
                parameters={
                    "type": "object",
                    "properties": {
                        "character_type": {
                            "type": "string",
                            "description": "Type of character (warrior, mage, rogue, etc.)"
                        },
                        "power_level": {
                            "type": "string",
                            "description": "Power level (beginner, intermediate, advanced, legendary)"
                        }
                    },
                    "required": ["character_type", "power_level"]
                }
            ),
            types.FunctionDeclaration(
                name="create_character_backstory",
                description="Generate a compelling backstory for the character including origin, motivation, and history",
                parameters={
                    "type": "object",
                    "properties": {
                        "character_name": {
                            "type": "string",
                            "description": "Name of the character"
                        },
                        "character_type": {
                            "type": "string",
                            "description": "Type/class of character"
                        },
                        "setting": {
                            "type": "string",
                            "description": "Game setting (fantasy, sci-fi, modern, post-apocalyptic, etc.)"
                        }
                    },
                    "required": ["character_name", "character_type", "setting"]
                }
            ),
            types.FunctionDeclaration(
                name="design_character_abilities",
                description="Create unique abilities, skills, and special powers for the character",
                parameters={
                    "type": "object",
                    "properties": {
                        "character_type": {
                            "type": "string",
                            "description": "Type of character"
                        },
                        "power_level": {
                            "type": "string",
                            "description": "Character power level"
                        },
                        "num_abilities": {
                            "type": "integer",
                            "description": "Number of abilities to generate (3-6)"
                        }
                    },
                    "required": ["character_type", "power_level", "num_abilities"]
                }
            ),
            types.FunctionDeclaration(
                name="generate_visual_appearance",
                description="Create detailed visual description for character appearance including physical features, clothing, and distinctive marks",
                parameters={
                    "type": "object",
                    "properties": {
                        "character_type": {
                            "type": "string",
                            "description": "Type of character"
                        },
                        "setting": {
                            "type": "string",
                            "description": "Game setting/world"
                        },
                        "style": {
                            "type": "string",
                            "description": "Art style (realistic, anime, pixel art, comic book, etc.)"
                        }
                    },
                    "required": ["character_type", "setting"]
                }
            ),
            types.FunctionDeclaration(
                name="create_character_equipment",
                description="Generate equipment, weapons, armor, and items for the character",
                parameters={
                    "type": "object",
                    "properties": {
                        "character_type": {
                            "type": "string",
                            "description": "Type of character"
                        },
                        "power_level": {
                            "type": "string",
                            "description": "Character power level"
                        },
                        "setting": {
                            "type": "string",
                            "description": "Game setting"
                        }
                    },
                    "required": ["character_type", "power_level", "setting"]
                }
            ),
            types.FunctionDeclaration(
                name="generate_character_personality",
                description="Create personality traits, quirks, and behavioral patterns for the character",
                parameters={
                    "type": "object",
                    "properties": {
                        "character_name": {
                            "type": "string",
                            "description": "Character name"
                        },
                        "backstory_summary": {
                            "type": "string",
                            "description": "Brief backstory summary"
                        }
                    },
                    "required": ["character_name"]
                }
            )
        ]
    )
]


# Tool implementation functions
def generate_character_attributes(character_type, power_level):
    """Generate character attributes based on type and power level"""
    base_stats = {
        "warrior": {"strength": 8, "intelligence": 4, "agility": 6, "charisma": 5, "vitality": 9, "wisdom": 4},
        "mage": {"strength": 3, "intelligence": 10, "agility": 4, "charisma": 6, "vitality": 5, "wisdom": 9},
        "rogue": {"strength": 5, "intelligence": 6, "agility": 10, "charisma": 7, "vitality": 6, "wisdom": 5},
        "paladin": {"strength": 7, "intelligence": 5, "agility": 5, "charisma": 8, "vitality": 8, "wisdom": 7},
        "ranger": {"strength": 6, "intelligence": 6, "agility": 8, "charisma": 5, "vitality": 7, "wisdom": 7},
        "cleric": {"strength": 5, "intelligence": 7, "agility": 4, "charisma": 7, "vitality": 7, "wisdom": 10}
    }

    # Get base stats or use balanced default
    stats = base_stats.get(character_type.lower(), {
        "strength": 6, "intelligence": 6, "agility": 6, "charisma": 6, "vitality": 6, "wisdom": 6
    })

    # Adjust based on power level
    multipliers = {
        "beginner": 0.7,
        "intermediate": 1.0,
        "advanced": 1.3,
        "legendary": 1.6
    }

    multiplier = multipliers.get(power_level.lower(), 1.0)
    adjusted_stats = {k: int(v * multiplier) for k, v in stats.items()}

    return {
        "attributes": adjusted_stats,
        "total_power": sum(adjusted_stats.values()),
        "power_level": power_level
    }


def create_character_backstory(character_name, character_type, setting):
    """Generate character backstory"""
    templates = {
        "fantasy": f"{character_name} was born in the mystical lands of {setting}, where magic flows through the very air.",
        "sci-fi": f"{character_name} emerged from the advanced civilizations of {setting}, shaped by technology and exploration.",
        "modern": f"{character_name} grew up in the contemporary world of {setting}, facing challenges of modern society.",
        "post-apocalyptic": f"{character_name} survived the fall of civilization in {setting}, forged in fire and chaos."
    }

    base_story = templates.get(setting.lower(), f"{character_name} comes from the world of {setting}.")

    return {
        "origin": base_story,
        "motivation": f"As a {character_type}, {character_name} seeks to master their craft and make their mark on the world.",
        "defining_moment": f"A pivotal event in {character_name}'s past shaped them into the {character_type} they are today."
    }


def design_character_abilities(character_type, power_level, num_abilities):
    """Generate character abilities"""
    ability_templates = {
        "warrior": ["Mighty Strike", "Shield Bash", "Battle Cry", "Whirlwind Attack", "Defensive Stance", "Berserker Rage"],
        "mage": ["Fireball", "Ice Shard", "Lightning Bolt", "Teleport", "Mana Shield", "Arcane Blast"],
        "rogue": ["Backstab", "Shadow Step", "Poison Blade", "Smoke Bomb", "Pickpocket", "Evasion"],
        "paladin": ["Holy Strike", "Divine Shield", "Lay on Hands", "Consecration", "Aura of Protection", "Judgment"],
        "ranger": ["Multi-Shot", "Animal Companion", "Tracking", "Nature's Blessing", "Camouflage", "Deadly Aim"],
        "cleric": ["Heal", "Smite", "Resurrect", "Holy Ward", "Turn Undead", "Divine Light"]
    }

    abilities = ability_templates.get(character_type.lower(), ["Basic Attack", "Special Move", "Ultimate Ability"])
    selected = abilities[:min(num_abilities, len(abilities))]

    return {
        "abilities": [
            {"name": ability, "type": "active", "power_level": power_level}
            for ability in selected
        ]
    }


def generate_visual_appearance(character_type, setting, style="realistic"):
    """Generate visual appearance description"""
    return {
        "physical_description": f"A {character_type} with distinctive features befitting the {setting} world",
        "clothing": f"Wears traditional {character_type} attire appropriate for {setting}",
        "distinctive_features": f"Marked by their {character_type} training and experiences",
        "art_style": style,
        "color_palette": "Rich and vibrant colors matching their role"
    }


def create_character_equipment(character_type, power_level, setting):
    """Generate character equipment"""
    equipment_sets = {
        "warrior": {"weapon": "Sword", "armor": "Heavy Plate", "accessory": "Battle Standard"},
        "mage": {"weapon": "Staff", "armor": "Robes", "accessory": "Spellbook"},
        "rogue": {"weapon": "Dual Daggers", "armor": "Leather Armor", "accessory": "Lockpicks"},
        "paladin": {"weapon": "Holy Mace", "armor": "Blessed Armor", "accessory": "Sacred Symbol"},
        "ranger": {"weapon": "Longbow", "armor": "Studded Leather", "accessory": "Quiver"},
        "cleric": {"weapon": "Mace", "armor": "Chainmail", "accessory": "Holy Symbol"}
    }

    equipment = equipment_sets.get(character_type.lower(), {
        "weapon": "Basic Weapon", "armor": "Basic Armor", "accessory": "Common Item"
    })

    return {
        "weapon": equipment["weapon"],
        "armor": equipment["armor"],
        "accessory": equipment["accessory"],
        "quality": power_level
    }


def generate_character_personality(character_name, backstory_summary=""):
    """Generate personality traits"""
    return {
        "traits": ["Brave", "Determined", "Loyal"],
        "quirks": [f"{character_name} has a unique way of approaching challenges"],
        "values": ["Honor", "Justice", "Compassion"],
        "flaws": ["Can be overly confident", "Sometimes acts before thinking"]
    }


# Function dispatcher
FUNCTION_HANDLERS = {
    "generate_character_attributes": generate_character_attributes,
    "create_character_backstory": create_character_backstory,
    "design_character_abilities": design_character_abilities,
    "generate_visual_appearance": generate_visual_appearance,
    "create_character_equipment": create_character_equipment,
    "generate_character_personality": generate_character_personality
}


def create_character_with_agent(description):
    """
    Use Gemini agent with function calling to create a character

    Args:
        description: User's character description

    Returns:
        dict: Complete character data
    """
    print(f"\n=== Creating character from description ===")
    print(f"Description: {description}")

    # System instruction for the agent
    system_instruction = """
You are an expert game character designer AI agent. Your role is to help create compelling,
well-balanced game characters based on user descriptions.

CRITICAL INSTRUCTIONS:
1. Call each tool EXACTLY ONCE - never call the same tool multiple times
2. Once you receive a result from a tool, do NOT call that tool again
3. After calling all 6 tools (attributes, backstory, abilities, appearance, equipment, personality),
   immediately provide the final character summary
4. Do NOT try to "improve" or "refine" the character by calling tools again

Tool calling workflow:
Step 1: Call generate_character_attributes ONCE
Step 2: Call create_character_backstory ONCE
Step 3: Call design_character_abilities ONCE
Step 4: Call generate_visual_appearance ONCE
Step 5: Call create_character_equipment ONCE
Step 6: Call generate_character_personality ONCE
Step 7: Provide final synthesis - DO NOT CALL ANY MORE TOOLS

Available tools (use each EXACTLY ONCE):
- generate_character_attributes: For stats and attributes
- create_character_backstory: For character history
- design_character_abilities: For skills and powers
- generate_visual_appearance: For physical description
- create_character_equipment: For items and gear
- generate_character_personality: For traits and quirks

Remember: Each tool provides valid results. Accept them and move forward. Never repeat tool calls.
"""

    try:
        # Initial message
        user_message = f"""
Create a complete game character based on this description:

{description}

IMPORTANT: Use each tool EXACTLY ONCE, then provide the final summary. Do NOT call tools multiple times.

Required workflow:
1. Call generate_character_attributes once
2. Call create_character_backstory once
3. Call design_character_abilities once (with num_abilities=5)
4. Call generate_visual_appearance once
5. Call create_character_equipment once
6. Call generate_character_personality once
7. Provide final character summary

After step 6, STOP calling tools and give me the complete character summary.
"""

        # Build conversation contents - CRITICAL for thought signatures
        # We must manually track the full conversation history
        contents = [
            types.Content(
                role="user",
                parts=[types.Part(text=user_message)]
            )
        ]

        print(f"\nSending message to agent...")

        # Use generate_content instead of chat to have full control
        response = client.models.generate_content(
            model=MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                tools=TOOLS,
                temperature=0.9,
                thinking_config=types.ThinkingConfig(include_thoughts=True),
                tool_config=types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(
                        mode="auto"  # Let model decide when to stop calling tools
                    )
                )
            )
        )

        character_data = {
            "description": description,
            "attributes": {},
            "backstory": {},
            "abilities": {},
            "appearance": {},
            "equipment": {},
            "personality": {},
            "reasoning_chain": [],  # Track agent's reasoning steps
            "_processed_tool_ids": set(),  # Track which tools we've already recorded
            "_all_tools_called": False  # Flag to track if all 6 tools have been called
        }

        # Handle function calls (max 10 iterations as safety)
        max_iterations = 10
        iteration = 0

        # Track which tools have been called
        required_tools = {
            "generate_character_attributes",
            "create_character_backstory",
            "design_character_abilities",
            "generate_visual_appearance",
            "create_character_equipment",
            "generate_character_personality"
        }
        called_tools = set()

        while iteration < max_iterations:
            iteration += 1
            print(f"\n--- Iteration {iteration} ---")
            print(f"Current reasoning chain length: {len(character_data['reasoning_chain'])}")
            print(f"Processed tool IDs: {character_data['_processed_tool_ids']}")

            # Check if response is valid
            if not hasattr(response, 'candidates') or not response.candidates:
                print("No candidates in response")
                break

            candidate = response.candidates[0]
            if not hasattr(candidate, 'content') or not candidate.content:
                print("No content in candidate")
                break

            if not hasattr(candidate.content, 'parts') or not candidate.content.parts:
                print("No parts in content")
                break

            parts = candidate.content.parts
            has_function_call = False

            # CRITICAL: Add the full model Content object to contents
            # This preserves the thought_signature that the model returned
            contents.append(candidate.content)

            function_responses = []

            for part in parts:
                # Check for function call
                if hasattr(part, 'function_call') and part.function_call:
                    has_function_call = True
                    func_call = part.function_call
                    func_name = func_call.name
                    func_args = dict(func_call.args) if hasattr(func_call, 'args') else {}
                    func_id = func_call.id if hasattr(func_call, 'id') else None  # Capture the ID

                    # Check if we've already processed this exact function call
                    already_processed = func_id and func_id in character_data["_processed_tool_ids"]

                    if already_processed:
                        print(f"\n⚠️ SKIPPING already processed tool: {func_name} (ID: {func_id})")
                        # Don't execute again, but we might still need to send a response
                        # For now, just skip entirely since this shouldn't happen in normal flow
                        continue

                    print(f"\nAgent calling tool: {func_name}")
                    print(f"Arguments: {func_args}")
                    if func_id:
                        print(f"Function Call ID: {func_id}")

                    # Track which tool was called
                    called_tools.add(func_name)

                    # Execute the function
                    if func_name in FUNCTION_HANDLERS:
                        try:
                            result = FUNCTION_HANDLERS[func_name](**func_args)
                            print(f"Result: {result}")

                            # Store result in character data
                            if "attributes" in func_name:
                                character_data["attributes"] = result
                            elif "backstory" in func_name:
                                character_data["backstory"] = result
                            elif "abilities" in func_name:
                                character_data["abilities"] = result
                            elif "appearance" in func_name:
                                character_data["appearance"] = result
                            elif "equipment" in func_name:
                                character_data["equipment"] = result
                            elif "personality" in func_name:
                                character_data["personality"] = result

                            # Add to reasoning chain (we already checked it's not a duplicate)
                            step_num = len(character_data["reasoning_chain"]) + 1
                            character_data["reasoning_chain"].append({
                                "step": step_num,
                                "tool": func_name,
                                "arguments": func_args,
                                "result": result,
                                "status": "success"
                            })
                            print(f"✅ Added step {step_num} to reasoning chain: {func_name}")

                            # Mark this function call as processed
                            if func_id:
                                character_data["_processed_tool_ids"].add(func_id)
                                print(f"📝 Marked ID as processed: {func_id}")

                            # CRITICAL: Create FunctionResponse with ID to match with the call
                            func_response = types.FunctionResponse(
                                name=func_name,
                                response={"result": result}
                            )
                            # Set ID if available (Gemini 3 requires this)
                            if func_id:
                                func_response.id = func_id

                            function_responses.append(
                                types.Part(function_response=func_response)
                            )
                        except Exception as e:
                            print(f"Error executing {func_name}: {e}")
                            import traceback
                            traceback.print_exc()

                            # Add error to reasoning chain (we already checked it's not a duplicate)
                            character_data["reasoning_chain"].append({
                                "step": len(character_data["reasoning_chain"]) + 1,
                                "tool": func_name,
                                "arguments": func_args,
                                "error": str(e),
                                "status": "error"
                            })

                            # Mark this function call as processed
                            if func_id:
                                character_data["_processed_tool_ids"].add(func_id)

                            # Create error response with ID
                            func_response = types.FunctionResponse(
                                name=func_name,
                                response={"error": str(e)}
                            )
                            if func_id:
                                func_response.id = func_id

                            function_responses.append(
                                types.Part(function_response=func_response)
                            )

            if not has_function_call:
                # Agent finished calling tools, get final text
                final_text = ""
                for part in parts:
                    if hasattr(part, 'text') and part.text:
                        final_text += part.text

                if final_text:
                    print(f"\nAgent final response:\n{final_text}")
                    character_data["summary"] = final_text
                break

            # Check if all required tools have been called at least once
            if called_tools >= required_tools:
                print(f"\n✅ All 6 required tools have been called!")
                print(f"Called tools: {called_tools}")
                character_data["_all_tools_called"] = True
                # Force the agent to finish by not allowing more tool calls
                # We'll break after this iteration

            # Send function responses back to agent
            if function_responses:
                num_responses = len(function_responses)
                print(f"\nSending {num_responses} function responses back to agent...")

                # Add function responses to contents.
                # For the Gemini API (ai.google.dev), functionResponse parts
                # are sent inside a "user" turn, matching the official docs.
                contents.append(
                    types.Content(
                        role="user",
                        parts=function_responses
                    )
                )

                # If all tools have been called, send a message to force completion
                if character_data["_all_tools_called"]:
                    print("\n🛑 Forcing agent to complete - all tools have been called")
                    contents.append(
                        types.Content(
                            role="user",
                            parts=[types.Part(text="All required tools have been called. Please provide the final character summary now. Do NOT call any more tools.")]
                        )
                    )

                # Send the FULL contents array (includes all thought signatures)
                # If all tools have been called, disable function calling to force text response
                tool_calling_mode = "none" if character_data["_all_tools_called"] else "auto"

                response = client.models.generate_content(
                    model=MODEL,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        tools=TOOLS if not character_data["_all_tools_called"] else None,
                        temperature=0.9,
                        thinking_config=types.ThinkingConfig(include_thoughts=True),
                        tool_config=types.ToolConfig(
                            function_calling_config=types.FunctionCallingConfig(
                                mode=tool_calling_mode
                            )
                        ) if not character_data["_all_tools_called"] else None
                    )
                )

        print(f"\n=== Character creation complete ===")

        # Clean up internal tracking fields before returning
        if "_processed_tool_ids" in character_data:
            del character_data["_processed_tool_ids"]
        if "_all_tools_called" in character_data:
            del character_data["_all_tools_called"]

        return character_data

    except Exception as e:
        print(f"Error in agent character creation: {e}")
        import traceback
        traceback.print_exc()
        return None


def generate_character_image(character_data):
    """
    Generate character image using gemini-2.5-flash-image (Nano Banana)

    Args:
        character_data: Complete character data dict

    Returns:
        str: Base64 encoded image data
    """
    print("\n=== Generating character image ===")

    try:
        # Build detailed prompt from character data
        appearance = character_data.get("appearance", {})
        equipment = character_data.get("equipment", {})
        backstory = character_data.get("backstory", {})

        # Extract key details
        character_type = character_data.get("description", "fantasy character")
        style = appearance.get("art_style", "realistic fantasy")
        physical_desc = appearance.get("physical_description", "")
        clothing = appearance.get("clothing", "")

        # Build comprehensive prompt
        prompt = f"""
Create a detailed character portrait for a game:

Character Type: {character_type}
Art Style: {style}
Physical Appearance: {physical_desc}
Clothing: {clothing}
Equipment: Wielding {equipment.get('weapon', 'a weapon')}, wearing {equipment.get('armor', 'armor')}

High quality, detailed, professional game character art, full body portrait,
dramatic lighting, {style} style, centered composition
"""

        print(f"Image prompt: {prompt}")

        # For gemini-2.5-flash-image (Nano Banana), use generate_content with IMAGE modality
        response = client.models.generate_content(
            model=IMAGE_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                image_config=types.ImageConfig(
                    aspect_ratio="1:1",
                )
            )
        )

        # Extract image from response
        if response and response.candidates:
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'inline_data') and part.inline_data:
                    # Get image bytes
                    image_bytes = part.inline_data.data
                    mime_type = part.inline_data.mime_type

                    # Convert to base64
                    base64_image = base64.b64encode(image_bytes).decode('utf-8')
                    print(f"Image generated successfully ({mime_type})")
                    return f"data:{mime_type};base64,{base64_image}"

        print("No image generated in response")
        return None

    except Exception as e:
        print(f"Error generating image: {e}")
        import traceback
        traceback.print_exc()
        return None


# Test function
if __name__ == "__main__":
    print("AI Character Designer - Gemini Service")
    print("Testing character creation...")

    test_description = "A brave elven ranger from a mystical forest, skilled with bow and nature magic"

    character = create_character_with_agent(test_description)

    if character:
        print("\n=== Character Created ===")
        print(json.dumps(character, indent=2))

        # Try to generate image
        # image = generate_character_image(character)
        # if image:
        #     print("Image generated successfully")
