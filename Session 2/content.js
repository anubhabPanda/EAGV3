// Content script for extracting hotel data from web pages

console.log('Hotel Comparison content script loaded');

// Listen for messages from background script
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'GET_PAGE_HTML') {
    try {
      // Get relevant page content
      const pageData = {
        html: document.documentElement.outerHTML,
        url: window.location.href,
        title: document.title,
        // Try to get meta tags that might contain hotel info
        metaTags: {
          ogTitle: document.querySelector('meta[property="og:title"]')?.content,
          ogImage: document.querySelector('meta[property="og:image"]')?.content,
          ogDescription: document.querySelector('meta[property="og:description"]')?.content,
        }
      };

      sendResponse({ success: true, pageData: pageData });
    } catch (error) {
      sendResponse({ success: false, error: error.message });
    }
    return true;
  }
});

// Helper function to extract visible text (could be useful for simpler extraction)
function getVisibleText() {
  return document.body.innerText;
}
