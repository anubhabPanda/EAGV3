// AI Character Designer - Sidebar Script

const API_BASE_URL = 'http://localhost:5001/api';

// DOM Elements
const descriptionInput = document.getElementById('character-description');
const createBtn = document.getElementById('create-character-btn');
const loading = document.getElementById('loading');
const characterDisplay = document.getElementById('character-display');
const characterImage = document.getElementById('character-image');
const imageLoading = document.getElementById('image-loading');
const imagePlaceholder = document.getElementById('image-placeholder');
const regenerateImageBtn = document.getElementById('regenerate-image-btn');
const saveCharacterBtn = document.getElementById('save-character-btn');
const newCharacterBtn = document.getElementById('new-character-btn');
const exportJsonBtn = document.getElementById('export-json-btn');
const clearAllBtn = document.getElementById('clear-all-btn');
const characterCount = document.getElementById('character-count');
const savedCharactersList = document.getElementById('saved-characters-list');

// Reasoning chain elements
const toggleReasoningBtn = document.getElementById('toggle-reasoning-btn');
const reasoningChain = document.getElementById('reasoning-chain');
const reasoningStepCount = document.getElementById('reasoning-step-count');

// Content containers
const attributesContent = document.getElementById('attributes-content');
const backstoryContent = document.getElementById('backstory-content');
const abilitiesContent = document.getElementById('abilities-content');
const appearanceContent = document.getElementById('appearance-content');
const equipmentContent = document.getElementById('equipment-content');
const personalityContent = document.getElementById('personality-content');
const summaryContent = document.getElementById('summary-content');

// State
let currentCharacter = null;
let savedCharacters = [];

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  loadSavedCharacters();
  setupEventListeners();
});

// Event Listeners
function setupEventListeners() {
  createBtn.addEventListener('click', createCharacter);
  regenerateImageBtn.addEventListener('click', regenerateImage);
  saveCharacterBtn.addEventListener('click', saveCharacter);
  newCharacterBtn.addEventListener('click', resetForm);
  exportJsonBtn.addEventListener('click', exportCharacterJson);
  clearAllBtn.addEventListener('click', clearAllCharacters);
  toggleReasoningBtn.addEventListener('click', toggleReasoningChain);
}

// Toggle Reasoning Chain
function toggleReasoningChain() {
  const icon = toggleReasoningBtn.querySelector('.toggle-icon');
  const isOpen = reasoningChain.style.display === 'block';

  if (isOpen) {
    reasoningChain.style.display = 'none';
    icon.classList.remove('open');
  } else {
    reasoningChain.style.display = 'block';
    icon.classList.add('open');
  }
}

// Create Character
async function createCharacter() {
  const description = descriptionInput.value.trim();
  
  if (!description) {
    alert('Please enter a character description');
    return;
  }
  
  try {
    // Show loading
    loading.style.display = 'block';
    characterDisplay.style.display = 'none';
    createBtn.disabled = true;
    
    console.log('Creating character:', description);
    
    // Call API
    const response = await fetch(`${API_BASE_URL}/create-character`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ description })
    });
    
    if (!response.ok) {
      throw new Error('Failed to create character');
    }
    
    const data = await response.json();
    
    if (!data.success) {
      throw new Error(data.error || 'Character creation failed');
    }
    
    console.log('Character created:', data.character);
    
    currentCharacter = data.character;
    
    // Display character
    displayCharacter(data.character);
    
    // Generate image
    generateImage(data.character);
    
    // Show character display
    loading.style.display = 'none';
    characterDisplay.style.display = 'flex';
    
  } catch (error) {
    console.error('Error creating character:', error);
    alert('Error: ' + error.message);
    loading.style.display = 'none';
    createBtn.disabled = false;
  }
}

// Display Character
function displayCharacter(character) {
  console.log('Displaying character:', character);

  // Display reasoning chain
  displayReasoningChain(character.reasoning_chain || []);

  // Attributes
  if (character.attributes && character.attributes.attributes) {
    const attrs = character.attributes.attributes;
    attributesContent.innerHTML = `
      <div class="stat-grid">
        ${Object.entries(attrs).map(([key, value]) => `
          <div class="stat-item">
            <span class="stat-name">${key}</span>
            <span class="stat-value">${value}</span>
          </div>
        `).join('')}
      </div>
      <p style="margin-top: 12px; font-weight: 600; color: #667eea;">
        Total Power: ${character.attributes.total_power || 'N/A'}
      </p>
    `;
  }
  
  // Backstory
  if (character.backstory) {
    const backstory = character.backstory;
    backstoryContent.innerHTML = `
      <p><strong>Origin:</strong> ${backstory.origin || 'N/A'}</p>
      <p style="margin-top: 8px;"><strong>Motivation:</strong> ${backstory.motivation || 'N/A'}</p>
      <p style="margin-top: 8px;"><strong>Defining Moment:</strong> ${backstory.defining_moment || 'N/A'}</p>
    `;
  }
  
  // Abilities
  if (character.abilities && character.abilities.abilities) {
    const abilities = character.abilities.abilities;
    abilitiesContent.innerHTML = `
      <div class="ability-list">
        ${abilities.map(ability => `
          <div class="ability-item">
            <div class="ability-name">${ability.name}</div>
            <div class="ability-type">${ability.type} • ${ability.power_level}</div>
          </div>
        `).join('')}
      </div>
    `;
  }
  
  // Appearance
  if (character.appearance) {
    const appearance = character.appearance;
    appearanceContent.innerHTML = `
      <p><strong>Physical:</strong> ${appearance.physical_description || 'N/A'}</p>
      <p style="margin-top: 8px;"><strong>Clothing:</strong> ${appearance.clothing || 'N/A'}</p>
      <p style="margin-top: 8px;"><strong>Distinctive Features:</strong> ${appearance.distinctive_features || 'N/A'}</p>
      <p style="margin-top: 8px;"><strong>Art Style:</strong> ${appearance.art_style || 'N/A'}</p>
    `;
  }

  // Equipment
  if (character.equipment) {
    const equipment = character.equipment;
    equipmentContent.innerHTML = `
      <p><strong>Weapon:</strong> ${equipment.weapon || 'N/A'}</p>
      <p style="margin-top: 8px;"><strong>Armor:</strong> ${equipment.armor || 'N/A'}</p>
      <p style="margin-top: 8px;"><strong>Accessory:</strong> ${equipment.accessory || 'N/A'}</p>
      <p style="margin-top: 8px;"><strong>Quality:</strong> ${equipment.quality || 'N/A'}</p>
    `;
  }

  // Personality
  if (character.personality) {
    const personality = character.personality;
    personalityContent.innerHTML = `
      <p><strong>Traits:</strong> ${personality.traits?.join(', ') || 'N/A'}</p>
      <p style="margin-top: 8px;"><strong>Values:</strong> ${personality.values?.join(', ') || 'N/A'}</p>
      <p style="margin-top: 8px;"><strong>Quirks:</strong> ${personality.quirks?.join('. ') || 'N/A'}</p>
      <p style="margin-top: 8px;"><strong>Flaws:</strong> ${personality.flaws?.join(', ') || 'N/A'}</p>
    `;
  }

  // Summary
  if (character.summary) {
    summaryContent.innerHTML = `<p>${character.summary}</p>`;
  }
}

// Display Reasoning Chain
function displayReasoningChain(steps) {
  if (!steps || steps.length === 0) {
    reasoningChain.innerHTML = '<p style="text-align: center; color: #6b7280; padding: 20px;">No reasoning steps available</p>';
    reasoningStepCount.textContent = '0 steps';
    return;
  }

  reasoningStepCount.textContent = `${steps.length} step${steps.length > 1 ? 's' : ''}`;

  const toolIcons = {
    'generate_character_attributes': '⚔️',
    'create_character_backstory': '📜',
    'design_character_abilities': '💫',
    'generate_visual_appearance': '👤',
    'create_character_equipment': '🛡️',
    'generate_character_personality': '🎭'
  };

  const toolNames = {
    'generate_character_attributes': 'Generate Attributes',
    'create_character_backstory': 'Create Backstory',
    'design_character_abilities': 'Design Abilities',
    'generate_visual_appearance': 'Generate Appearance',
    'create_character_equipment': 'Create Equipment',
    'generate_character_personality': 'Generate Personality'
  };

  reasoningChain.innerHTML = steps.map(step => {
    const icon = toolIcons[step.tool] || '🔧';
    const toolName = toolNames[step.tool] || step.tool;
    const isError = step.status === 'error';
    const statusIcon = isError ? '❌' : '✅';

    // Format arguments
    const argumentsHtml = Object.entries(step.arguments || {}).map(([key, value]) => `
      <div class="argument-item">
        <span class="argument-key">${key}:</span>
        <span class="argument-value">${value}</span>
      </div>
    `).join('');

    // Format result
    let resultHtml = '';
    if (isError) {
      resultHtml = `<div class="result-content">${step.error}</div>`;
    } else {
      resultHtml = `<div class="result-content">${JSON.stringify(step.result, null, 2)}</div>`;
    }

    return `
      <div class="reasoning-step ${isError ? 'error' : ''}">
        <div class="step-header">
          <span class="step-number">Step ${step.step}</span>
          <span class="step-status">${statusIcon}</span>
        </div>
        <div class="tool-name">
          <span class="tool-icon">${icon}</span>
          ${toolName}
        </div>
        ${argumentsHtml ? `
          <div class="step-arguments">
            <div class="step-arguments-title">Arguments</div>
            ${argumentsHtml}
          </div>
        ` : ''}
        <div class="step-result">
          <div class="step-result-title">${isError ? 'Error' : 'Result'}</div>
          ${resultHtml}
        </div>
      </div>
    `;
  }).join('');
}

// Generate Image
async function generateImage(character) {
  try {
    // Show loading state
    imageLoading.style.display = 'flex';
    characterImage.style.display = 'none';
    imagePlaceholder.style.display = 'none';
    regenerateImageBtn.style.display = 'none';

    console.log('Generating image for character...');

    const response = await fetch(`${API_BASE_URL}/generate-image`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ character_data: character })
    });

    if (!response.ok) {
      throw new Error('Failed to generate image');
    }

    const data = await response.json();

    if (data.success && data.image) {
      console.log('Image generated successfully');

      // Display image
      characterImage.src = data.image;
      characterImage.style.display = 'block';
      imageLoading.style.display = 'none';
      regenerateImageBtn.style.display = 'block';

      // Store image in character data
      currentCharacter.image = data.image;
    } else {
      throw new Error(data.error || 'Image generation failed');
    }

  } catch (error) {
    console.error('Error generating image:', error);

    // Show placeholder
    imageLoading.style.display = 'none';
    imagePlaceholder.style.display = 'flex';
    regenerateImageBtn.style.display = 'block';
  }
}

// Regenerate Image
async function regenerateImage() {
  if (currentCharacter) {
    await generateImage(currentCharacter);
  }
}

// Save Character
async function saveCharacter() {
  if (!currentCharacter) {
    alert('No character to save');
    return;
  }

  // Generate a name if not present
  const characterName = prompt('Enter a name for this character:', extractCharacterName());

  if (!characterName) {
    return;
  }

  const characterToSave = {
    ...currentCharacter,
    name: characterName,
    timestamp: new Date().toISOString()
  };

  // Add to background storage
  const response = await chrome.runtime.sendMessage({
    type: 'ADD_CHARACTER',
    character: characterToSave
  });

  if (response && response.success) {
    alert('Character saved!');
    loadSavedCharacters();
  }
}

// Extract character name from description or attributes
function extractCharacterName() {
  if (currentCharacter.description) {
    // Try to extract first word as name
    const words = currentCharacter.description.split(' ');
    return words[1] || 'Character';
  }
  return 'Character';
}

// Load Saved Characters
async function loadSavedCharacters() {
  const response = await chrome.runtime.sendMessage({ type: 'GET_CHARACTERS' });

  if (response && response.characters) {
    savedCharacters = response.characters;
    characterCount.textContent = savedCharacters.length;
    renderSavedCharacters();
  }
}

// Render Saved Characters
function renderSavedCharacters() {
  if (savedCharacters.length === 0) {
    savedCharactersList.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">🎮</div>
        <p>No saved characters yet</p>
      </div>
    `;
    return;
  }

  savedCharactersList.innerHTML = savedCharacters.map((char, index) => `
    <div class="saved-character-card" data-index="${index}">
      <div class="saved-character-name">${char.name || 'Unnamed Character'}</div>
      <div class="saved-character-type">${char.description?.substring(0, 60) || 'Character'}...</div>
    </div>
  `).join('');

  // Add click listeners
  document.querySelectorAll('.saved-character-card').forEach(card => {
    card.addEventListener('click', () => {
      const index = parseInt(card.dataset.index);
      loadCharacterByIndex(index);
    });
  });
}

// Load Character by Index
function loadCharacterByIndex(index) {
  const character = savedCharacters[index];
  if (character) {
    currentCharacter = character;
    displayCharacter(character);
    characterDisplay.style.display = 'flex';

    // Load image if available
    if (character.image) {
      characterImage.src = character.image;
      characterImage.style.display = 'block';
      imageLoading.style.display = 'none';
      imagePlaceholder.style.display = 'none';
      regenerateImageBtn.style.display = 'block';
    }

    // Scroll to character display
    characterDisplay.scrollIntoView({ behavior: 'smooth' });
  }
}

// Reset Form
function resetForm() {
  descriptionInput.value = '';
  currentCharacter = null;
  characterDisplay.style.display = 'none';
  createBtn.disabled = false;
}

// Export Character as JSON
function exportCharacterJson() {
  if (!currentCharacter) {
    alert('No character to export');
    return;
  }

  const dataStr = JSON.stringify(currentCharacter, null, 2);
  const dataBlob = new Blob([dataStr], { type: 'application/json' });
  const url = URL.createObjectURL(dataBlob);

  const link = document.createElement('a');
  link.href = url;
  link.download = `${currentCharacter.name || 'character'}.json`;
  link.click();

  URL.revokeObjectURL(url);
}

// Clear All Characters
async function clearAllCharacters() {
  if (!confirm('Are you sure you want to delete all saved characters?')) {
    return;
  }

  const response = await chrome.runtime.sendMessage({ type: 'CLEAR_CHARACTERS' });

  if (response && response.success) {
    alert('All characters cleared');
    loadSavedCharacters();
  }
}

console.log('AI Character Designer sidebar loaded');

