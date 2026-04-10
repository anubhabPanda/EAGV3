// Background service worker for YouTube Controller
console.log('YouTube Controller: Background service worker loaded');

// Listen for extension installation
chrome.runtime.onInstalled.addListener(() => {
  console.log('YouTube Controller extension installed');
});

// Keep service worker alive
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  console.log('Background received message:', request);
  sendResponse({ received: true });
  return true;
});
