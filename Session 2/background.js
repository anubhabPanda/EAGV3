// Background service worker for hotel comparison extension

// State management
let hotels = [];
let userLocation = '';

// Load state from storage on startup
chrome.storage.local.get(['hotels', 'userLocation'], (result) => {
  if (result.hotels) {
    hotels = result.hotels;
    console.log('Loaded hotels from storage:', hotels.length);
  }
  if (result.userLocation) {
    userLocation = result.userLocation;
  }
});

// Save state to storage
function saveState() {
  chrome.storage.local.set({ hotels, userLocation }, () => {
    console.log('State saved to storage');
  });
}

// Listen for extension icon click to open side panel
chrome.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: true })
  .catch((error) => console.error(error));

// Listen for messages from content script and sidebar
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log('Background received message:', message.type);

  switch (message.type) {
    case 'GET_HOTELS':
      sendResponse({ hotels: hotels, location: userLocation });
      return true;

    case 'ADD_HOTEL':
      hotels.push(message.hotel);
      console.log('Hotel added to background. Total hotels:', hotels.length);
      console.log('Hotel name:', message.hotel.name);
      console.log('All hotels:', hotels.map(h => h.name));
      saveState(); // Persist to storage
      // Broadcast to sidebar
      chrome.runtime.sendMessage({ type: 'HOTEL_ADDED', hotel: message.hotel })
        .catch(() => {}); // Ignore if sidebar not open
      sendResponse({ success: true, total: hotels.length });
      return true;

    case 'REMOVE_HOTEL':
      hotels = hotels.filter((_, index) => index !== message.index);
      console.log('Hotel removed. Total hotels:', hotels.length);
      saveState(); // Persist to storage
      sendResponse({ success: true, hotels: hotels });
      return true;

    case 'CLEAR_HOTELS':
      hotels = [];
      console.log('All hotels cleared');
      saveState(); // Persist to storage
      sendResponse({ success: true });
      return true;

    case 'UPDATE_LOCATION':
      userLocation = message.location;
      console.log('Location updated:', userLocation);
      saveState(); // Persist to storage
      sendResponse({ success: true });
      return true;

    case 'EXTRACT_HOTEL_DATA':
      // Forward to content script
      chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        if (tabs[0]) {
          chrome.tabs.sendMessage(
            tabs[0].id,
            { type: 'GET_PAGE_HTML' },
            (response) => {
              sendResponse(response);
            }
          );
        } else {
          sendResponse({ success: false, error: 'No active tab' });
        }
      });
      return true;

    default:
      sendResponse({ success: false, error: 'Unknown message type' });
      return true;
  }
});

// Initialize when extension is installed
chrome.runtime.onInstalled.addListener(() => {
  console.log('Hotel Comparison Extension installed');
});
