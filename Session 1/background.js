// Background service worker to manage communication
let currentVideoState = {
  hasVideo: false,
  activeTabId: null
};

// Listen for messages from content scripts
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'VIDEO_STATE') {
    if (message.state.hasVideo) {
      currentVideoState = {
        ...message.state,
        activeTabId: sender.tab.id
      };
      
      // Update icon badge to indicate active video
      chrome.action.setBadgeText({ text: '▶' });
      chrome.action.setBadgeBackgroundColor({ color: '#FF0000' });
    }
  }
});

// Listen for messages from popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'GET_CURRENT_STATE') {
    sendResponse({ state: currentVideoState });
    return true;
  }
  
  if (message.type === 'SEND_COMMAND') {
    if (currentVideoState.activeTabId) {
      chrome.tabs.sendMessage(
        currentVideoState.activeTabId,
        message.command,
        (response) => {
          sendResponse(response);
        }
      );
      return true;
    } else {
      sendResponse({ success: false, error: 'No active YouTube video found' });
    }
  }
});

// Check for YouTube tabs periodically
async function checkYouTubeTabs() {
  const tabs = await chrome.tabs.query({ url: '*://*.youtube.com/*' });
  
  if (tabs.length === 0) {
    currentVideoState = {
      hasVideo: false,
      activeTabId: null
    };
    chrome.action.setBadgeText({ text: '' });
  }
}

// Check every 5 seconds
setInterval(checkYouTubeTabs, 5000);

// Listen for tab removal
chrome.tabs.onRemoved.addListener((tabId) => {
  if (tabId === currentVideoState.activeTabId) {
    currentVideoState = {
      hasVideo: false,
      activeTabId: null
    };
    chrome.action.setBadgeText({ text: '' });
  }
});
