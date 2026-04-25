// Background service worker for AI Character Designer

// State management
let characters = [];

// Listen for extension icon click to open side panel
chrome.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: true })
  .catch((error) => console.error(error));

// Message handling
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log('Background received message:', message.type);
  
  switch (message.type) {
    case 'GET_CHARACTERS':
      sendResponse({ success: true, characters: characters });
      return true;

    case 'ADD_CHARACTER':
      characters.push(message.character);
      console.log('Character added to background. Total characters:', characters.length);
      console.log('Character name:', message.character.name);
      
      // Save to storage
      chrome.storage.local.set({ characters }, () => {
        console.log('Characters saved to storage');
      });
      
      sendResponse({ success: true, total: characters.length });
      return true;

    case 'REMOVE_CHARACTER':
      characters = characters.filter((_, index) => index !== message.index);
      console.log('Character removed. Total characters:', characters.length);
      
      // Save to storage
      chrome.storage.local.set({ characters }, () => {
        console.log('Characters saved to storage');
      });
      
      sendResponse({ success: true, characters: characters });
      return true;

    case 'CLEAR_CHARACTERS':
      characters = [];
      console.log('All characters cleared');
      
      // Save to storage
      chrome.storage.local.set({ characters: [] }, () => {
        console.log('Characters cleared from storage');
      });
      
      sendResponse({ success: true });
      return true;

    default:
      sendResponse({ success: false, error: 'Unknown message type' });
      return true;
  }
});

// Load characters from storage on startup
chrome.storage.local.get(['characters'], (result) => {
  if (result.characters) {
    characters = result.characters;
    console.log('Loaded characters from storage:', characters.length);
  }
});

console.log('AI Character Designer background service worker loaded');
