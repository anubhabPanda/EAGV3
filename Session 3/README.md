# 🎮 AI Character Designer - Chrome Extension

An intelligent Chrome extension that helps game designers create complete, detailed characters using AI agents powered by Google Gemini. The extension uses function calling and tool orchestration to generate comprehensive character profiles with visual representations.

---

## DEMO LINK

[AI Character Design](https://youtu.be/BGUiVfTEdbI)

## ✨ Features

### 🤖 AI Agent-Based Character Creation
- **Intelligent Tool Orchestration**: Gemini 3 agent automatically decides which tools to use and in what order
- **Function Calling with Thought Signatures**: Advanced reasoning transparency with full thought chain tracking
- **6 Specialized Character Design Tools**:
  - 📊 **Attribute Generator**: Creates balanced character stats (strength, intelligence, agility, etc.)
  - 📜 **Backstory Creator**: Generates compelling character history and motivations
  - 💫 **Ability Designer**: Creates unique skills and special powers
  - 👤 **Appearance Generator**: Detailed visual descriptions and styling
  - 🛡️ **Equipment Creator**: Generates weapons, armor, and items
  - 🎭 **Personality Designer**: Creates traits, quirks, and behavioral patterns

### 🧠 Agent Reasoning Chain Visualization (NEW!)
- **Step-by-Step Transparency**: See exactly how the AI agent thinks and works
- **Beautiful UI**: Collapsible reasoning chain with animated cards
- **Tool Call Tracking**: View each tool called, arguments passed, and results returned
- **Success/Error Indicators**: Color-coded status for each step
- **Educational**: Learn how AI agents orchestrate complex workflows
- **Debugging Aid**: Identify issues in the character creation process

### 🎨 Visual Character Generation
- **AI Image Generation**: Uses `gemini-2.5-flash-image` (Nano Banana) for fast, high-quality character art
- **Multimodal Generation**: Leverages Gemini's native image generation capabilities
- **Prompt-based Art**: Converts character data into detailed image prompts
- **Multiple Art Styles**: Supports realistic fantasy, anime, pixel art, comic book styles
- **Regenerate Option**: Don't like the image? Generate a new one instantly

### 💾 Character Management
- **Save Characters**: Store your favorite character designs with full reasoning chains
- **Load Saved Characters**: Quickly access previously created characters
- **Export to JSON**: Download character data for use in games or other tools
- **Clear Management**: Remove individual characters or clear all at once

### 🎯 Smart Features
- **Context-Aware Design**: Agent understands relationships between character elements
- **Balanced Stats**: Automatic stat balancing based on character type and power level
- **Cohesive Profiles**: All character aspects work together harmoniously
- **Flexible Descriptions**: Works with any character description (fantasy, sci-fi, modern, etc.)
- **Efficient Tool Execution**: Agent calls each tool exactly once, then synthesizes results
- **Automatic Completion**: Stops after all 6 tools are called, preventing redundant iterations

---

## 🏗️ Architecture

### Agent-Based Workflow

```
┌─────────────────────────────────────────────────────────────┐
│                     User Description                         │
│        "A brave dwarf warrior from the mountains"           │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│              Gemini 3 Agent (Orchestrator)                  │
│         [Analyzes & Plans Tool Execution]                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
        ┌───────────────────────────────────┐
        │   ITERATION-BY-ITERATION FLOW     │
        └───────────────────────────────────┘
                            ↓
    Iteration 1: 📊 Generate Attributes
        → {'strength': 6, 'vitality': 6, ...}
                            ↓
    Iteration 2: 📜 Create Backstory
        → {'origin': '...', 'motivation': '...'}
                            ↓
    Iteration 3: 💫 Design Abilities
        → {'abilities': [Basic Attack, Special Move, ...]}
                            ↓
    Iteration 4: 👤 Generate Appearance
        → {'physical_description': '...', 'clothing': '...'}
                            ↓
    Iteration 5: 🛡️ Create Equipment
        → {'weapon': 'Basic Weapon', 'armor': '...'}
                            ↓
    Iteration 6: 🎭 Generate Personality
        → {'traits': ['Brave', 'Determined', ...]}
                            ↓
        ✅ All 6 Tools Called - Force Completion
                            ↓
    Iteration 7: 📝 Final Synthesis
        → Complete character profile with summary
                            ↓
┌─────────────────────────────────────────────────────────────┐
│              Complete Character Profile                      │
│         (All aspects coherently integrated)                  │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│         Image Generation (gemini-2.5-flash-image)           │
│              [Nano Banana - Fast Generation]                │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│        Final Character with AI-Generated Portrait            │
│         + Agent Reasoning Chain (6 transparent steps)       │
└─────────────────────────────────────────────────────────────┘
```

### Tech Stack

**Frontend (Chrome Extension)**:
- Chrome Extensions Manifest V3
- Vanilla JavaScript (ES6+)
- Modern CSS3 with Flexbox/Grid
- Chrome Side Panel API
- Chrome Storage API

**Backend (Python)**:
- Python 3.8+
- Flask (Web Framework)
- Google Gemini 3 Flash Preview (`gemini-3-flash-preview`)
- Google Gemini AI SDK (`google-genai>=1.3.0`)
- Gemini Image Model (`gemini-2.5-flash-image` - Nano Banana)
- Function Calling with Thought Signatures
- Pillow (Image Processing)

---

## 🚀 Installation

### Prerequisites
- Python 3.8 or higher
- Google Chrome browser
- Google Gemini API key ([Get it here](https://makersuite.google.com/app/apikey))

### Step 1: Install Dependencies

```bash
cd "Session 3"
pip install -r requirements.txt
```

### Step 2: Configure API Key

1. Copy the example environment file:
```bash
cp .env.example .env
```

2. Edit `.env` and add your Gemini API key:
```env
GEMINI_API_KEY=your_actual_api_key_here
```

### Step 3: Generate Extension Icons

```bash
python generate_icons.py
```

### Step 4: Load Extension in Chrome

1. Open Chrome and navigate to `chrome://extensions/`
2. Enable **Developer mode** (toggle in top-right corner)
3. Click **"Load unpacked"**
4. Select the `Session 3` folder
5. The extension should now appear in your toolbar! 🎮

### Step 5: Start the Backend Server

```bash
python server.py
```

**Keep this terminal window open while using the extension!**

The server will start on `http://localhost:5001`

---

## 📖 Usage

### Creating Your First Character

1. **Click the Extension Icon** in Chrome toolbar to open the sidebar

2. **Describe Your Character** in the text area. Be as detailed as you like:
   ```
   A brave elven ranger from a mystical forest, skilled with bow and 
   nature magic, wearing green leather armor with a silver emblem, 
   has a loyal wolf companion
   ```

3. **Click "Create Character"** and watch the magic happen!

4. **Wait for AI Agent** to orchestrate the character creation:
   - Agent analyzes your description
   - Calls appropriate tools in logical order
   - Generates all character aspects
   - Creates a cohesive profile

5. **View Character Details**:
   - ⚔️ Attributes (stats)
   - 📜 Backstory
   - 💫 Abilities
   - 👤 Appearance
   - 🛡️ Equipment
   - 🎭 Personality
   - 📝 Summary

6. **See Character Visualization**:
   - AI generates a unique character image
   - Based on all the character details
   - Can be regenerated if desired

7. **Save or Export**:
   - 💾 Save to your collection
   - 📄 Export as JSON file
   - 🔄 Create variations

---

## 🧠 Agent Execution Example

Here's a real example of the Gemini 3 agent creating a character step-by-step:

### User Input
```
A brave dwarf warrior from the mountains
```

### Agent Reasoning Chain (Backend Logs)

```plaintext
=== Creating character from description ===
Description: A brave dwarf warrior from the mountains

Sending message to agent...

--- Iteration 1 ---
Current reasoning chain length: 0
Processed tool IDs: set()

Agent calling tool: generate_character_attributes
Arguments: {'power_level': 'intermediate', 'character_type': 'dwarf warrior'}
Function Call ID: ag0wu14l
Result: {'attributes': {'strength': 6, 'intelligence': 6, 'agility': 6,
         'charisma': 6, 'vitality': 6, 'wisdom': 6}, 'total_power': 36}
✅ Added step 1 to reasoning chain: generate_character_attributes
📝 Marked ID as processed: ag0wu14l

--- Iteration 2 ---
Current reasoning chain length: 1
Processed tool IDs: {'ag0wu14l'}

Agent calling tool: create_character_backstory
Arguments: {'setting': 'high fantasy mountain kingdom',
           'character_name': 'Thrain Ironfoot',
           'character_type': 'dwarf warrior'}
Function Call ID: wzpq9dl7
Result: {'origin': 'Thrain Ironfoot comes from the world of high fantasy
         mountain kingdom.', 'motivation': 'As a dwarf warrior, Thrain
         Ironfoot seeks to master their craft...'}
✅ Added step 2 to reasoning chain: create_character_backstory
📝 Marked ID as processed: wzpq9dl7

--- Iteration 3 ---
Current reasoning chain length: 2

Agent calling tool: design_character_abilities
Arguments: {'num_abilities': 5, 'character_type': 'dwarf warrior',
           'power_level': 'intermediate'}
Function Call ID: 7fvjxn6c
Result: {'abilities': [{'name': 'Basic Attack', 'type': 'active'},
        {'name': 'Special Move', 'type': 'active'},
        {'name': 'Ultimate Ability', 'type': 'active'}]}
✅ Added step 3 to reasoning chain: design_character_abilities

--- Iteration 4 ---
Current reasoning chain length: 3

Agent calling tool: generate_visual_appearance
Arguments: {'setting': 'high fantasy mountain kingdom',
           'style': 'realistic fantasy',
           'character_type': 'dwarf warrior'}
Function Call ID: mg018mme
Result: {'physical_description': 'A dwarf warrior with distinctive features...',
        'clothing': 'Wears traditional dwarf warrior attire...'}
✅ Added step 4 to reasoning chain: generate_visual_appearance

--- Iteration 5 ---
Current reasoning chain length: 4

Agent calling tool: create_character_equipment
Arguments: {'character_type': 'dwarf warrior',
           'power_level': 'intermediate',
           'setting': 'high fantasy mountain kingdom'}
Function Call ID: tn39dj1c
Result: {'weapon': 'Basic Weapon', 'armor': 'Basic Armor',
        'accessory': 'Common Item', 'quality': 'intermediate'}
✅ Added step 5 to reasoning chain: create_character_equipment

--- Iteration 6 ---
Current reasoning chain length: 5

Agent calling tool: generate_character_personality
Arguments: {'character_name': 'Thrain Ironfoot',
           'backstory_summary': 'Thrain Ironfoot is a dwarf warrior from
            a high fantasy mountain kingdom...'}
Function Call ID: qix4g5lj
Result: {'traits': ['Brave', 'Determined', 'Loyal'],
        'quirks': ['Thrain Ironfoot has a unique way of approaching challenges'],
        'values': ['Honor', 'Justice', 'Compassion'],
        'flaws': ['Can be overly confident', 'Sometimes acts before thinking']}
✅ Added step 6 to reasoning chain: generate_character_personality

✅ All 6 required tools have been called!
Called tools: {'generate_character_attributes', 'create_character_backstory',
              'generate_visual_appearance', 'generate_character_personality',
              'create_character_equipment', 'design_character_abilities'}

🛑 Forcing agent to complete - all tools have been called

--- Iteration 7 ---
Current reasoning chain length: 6

Agent final response:
**Thrain Ironfoot: A Final Synthesis**

Here is the complete profile for **Thrain Ironfoot**, the brave dwarf warrior
from the mountains:

### **Character Profile: Thrain Ironfoot**
**Role:** Dwarf Warrior
**Origin:** High Fantasy Mountain Kingdom
**Power Level:** Intermediate

### **1. Attributes & Stats**
Thrain is a well-rounded combatant with balanced physical and mental capabilities.
*   **Strength:** 6 | **Vitality:** 6 | **Agility:** 6
*   **Intelligence:** 6 | **Wisdom:** 6 | **Charisma:** 6
*   **Total Power Score:** 36

### **2. Backstory**
Hailing from a legendary mountain kingdom, Thrain Ironfoot's life was forever
changed by a pivotal event that forged his resolve. He seeks to master the
martial crafts and leave a lasting legacy.

### **3. Abilities**
*   **Basic Attack:** A reliable, heavy strike
*   **Special Move:** A powerful tactical maneuver
*   **Ultimate Ability:** A devastating display of mountain-born strength

### **4. Personality & Traits**
*   **Traits:** Brave, Determined, Loyal
*   **Values:** Honor, Justice, Compassion
*   **Flaws:** Overly confident, acts before thinking
*   **Quirks:** Approaches challenges with unique, unconventional logic

### **5. Visual Appearance**
*   **Physical Description:** A stout, powerful warrior marked by training scars
*   **Attire:** Traditional dwarven armor with rich, vibrant clan colors
*   **Art Style:** Realistic Fantasy

### **6. Equipment**
*   **Weapon:** High-quality Basic Weapon (likely axe or hammer)
*   **Armor:** Sturdy Basic Armor from mountain ores
*   **Accessory:** A sentimental item for luck

=== Character creation complete ===

=== Generating character image ===
Image prompt: A brave dwarf warrior from the mountains, realistic fantasy style,
traditional dwarf warrior attire, wielding Basic Weapon, wearing Basic Armor...

✅ Character created with 6 reasoning steps
✅ AI-generated portrait ready
```

### What Happened?

1. **🎯 Agent Planning**: Gemini 3 agent analyzed the description and planned tool execution
2. **🔧 Sequential Tool Calls**: Called each of the 6 tools exactly once (iterations 1-6)
3. **🧠 Thought Signatures**: Each function call included a unique thought signature for transparency
4. **✅ Smart Completion**: After all 6 tools completed, agent automatically synthesized results
5. **🎨 Image Generation**: Final character data sent to `gemini-2.5-flash-image` for portrait
6. **📊 Reasoning Chain**: All 6 steps tracked and displayed in beautiful UI

**Total Time**: ~7 iterations
**Reasoning Steps**: 6 (one per tool)
**No Duplicates**: Each tool called exactly once ✅

---

## 🎯 Example Character Descriptions

Try these examples to see the AI agent in action:

### Fantasy
```
A wise old wizard with a long white beard, wearing star-patterned robes, 
carries an ancient oak staff, specializes in elemental magic
```

### Sci-Fi
```
A cybernetic soldier from the year 2157, enhanced with neural implants, 
expert in tactical combat and hacking, wears advanced exosuit armor
```

### Modern/Superhero
```
A street-smart vigilante with parkour skills and gadgets, fights crime 
at night, wears a tactical suit with grappling hooks and smoke bombs
```

### Post-Apocalyptic
```
A wasteland scavenger who survived the nuclear fallout, expert in 
survival and makeshift weapons, wears patched leather and gas mask
```

### Historical/Medieval
```
A noble knight from medieval England, sworn to protect the innocent,
master swordsman, wears plate armor with family crest
```

---

## 🔧 Technical Deep Dive

### Thought Signatures & Function Calling

This project uses **Gemini 3's advanced function calling with thought signatures**, which provides:

1. **Transparency**: Every function call includes a `thought_signature` that links the agent's reasoning to the action
2. **Traceability**: Full conversation history preserved, including all thought processes
3. **Debugging**: Easy to see exactly where issues occur in the agent workflow
4. **Unique IDs**: Each function call has a unique ID that links the call to its response

### Key Technical Fixes

#### 1. Thought Signature Compatibility
**Issue**: SDK v1.0.0 didn't support `thought_signature` field
**Fix**: Upgraded to `google-genai>=1.3.0` which added thought signature support (May 2025)

#### 2. Agent Loop Control
**Issue**: Agent calling tools repeatedly (30+ steps instead of 6)
**Fix**:
- Track which tools have been called using a set
- Force completion after all 6 tools executed
- Change function calling mode from `"any"` to `"auto"`
- Disable tools after completion with explicit message

#### 3. Reasoning Chain Deduplication
**Issue**: Same tool calls recorded multiple times
**Fix**: Use function call IDs to deduplicate - only record each unique ID once

#### 4. Image Generation Model
**Issue**: `gemini-2.5-flash-image` not compatible with `generate_images()` API
**Fix**: Use `generate_content()` with `response_modalities=["IMAGE"]` for Gemini image models

### Architecture

```
Frontend (Chrome Extension)
    ↓ [HTTP POST]
Flask Backend (Python)
    ↓ [API Call]
Google Gemini 3 Agent
    ↓ [Function Calls with Thought Signatures]
Tool Handlers (Python)
    ↓ [Return Results]
Gemini 3 Agent Synthesis
    ↓ [Complete Character]
gemini-2.5-flash-image
    ↓ [Generate Portrait]
Frontend Display + Reasoning Chain
```

---

## 🐛 Troubleshooting

### Issue: "Thought signature missing" error

**Symptom**: `400 INVALID_ARGUMENT: Function call is missing a thought_signature`

**Solution**:
```bash
# Upgrade google-genai SDK to version with thought signature support
pip install --upgrade google-genai
# Ensure version >= 1.3.0
```

### Issue: Duplicate reasoning steps

**Symptom**: Shows 20+ steps instead of 6

**Solution**: This was fixed in the latest version. Make sure you're running the updated code that:
- Tracks called tools with a set
- Forces completion after all 6 tools called
- Uses deduplication based on function call IDs

### Issue: Image generation fails with 404

**Symptom**: `404 NOT_FOUND: models/gemini-2.5-flash-image is not found for predict`

**Solution**: The code now uses `generate_content()` with `response_modalities=["IMAGE"]` instead of `generate_images()`. Make sure you have the latest version of `gemini_service.py`.

### Issue: Agent runs indefinitely

**Symptom**: Character creation never completes, keeps calling tools

**Solution**: Check that:
1. `max_iterations` is set (default: 10)
2. All 6 required tools are being called
3. The "force completion" logic is enabled after iteration 6

### Issue: API key errors

**Symptom**: `PERMISSION_DENIED` or `API key not valid`

**Solution**:
```bash
# Create .env file in Session 3 directory
echo "GEMINI_API_KEY=your_actual_api_key_here" > .env

# Verify the file exists
cat .env
```

---

## 📚 Documentation Files

- **`FINAL_SOLUTION.md`**: Complete guide to the thought signature fix
- **`IMAGE_GENERATION_FIX.md`**: How we fixed gemini-2.5-flash-image integration
- **`REASONING_CHAIN_FEATURE.md`**: Full documentation of the reasoning chain visualization
- **`REASONING_CHAIN_DUPLICATION_FIX.md`**: How we fixed duplicate steps
- **`AGENT_LOOP_FIX.md`**: How we fixed the infinite tool calling loop
- **`CORRECT_THOUGHT_SIGNATURE_FIX.md`**: Historical context on the thought signature journey

---

## 🎉 Key Achievements

✅ **Gemini 3 Integration**: Successfully integrated latest Gemini 3 Flash Preview model
✅ **Thought Signatures**: Full support for thought signatures and transparent reasoning
✅ **Agent Orchestration**: Smart tool calling with automatic completion detection
✅ **Reasoning Visualization**: Beautiful UI showing agent's step-by-step thinking
✅ **Image Generation**: Fast character portraits using gemini-2.5-flash-image
✅ **No Duplicates**: Robust deduplication ensuring each tool called exactly once
✅ **Production Ready**: Comprehensive error handling and logging

---

