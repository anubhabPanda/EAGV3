// Content script that runs on YouTube pages
(function() {
  'use strict';

  let video = null;
  let updateInterval = null;

  // Function to get the video element
  function getVideo() {
    return document.querySelector('video');
  }

  // Function to get video state
  function getVideoState() {
    video = getVideo();
    
    if (!video) {
      return { hasVideo: false };
    }

    // Get thumbnail from video or page
    let thumbnail = null;
    const metaThumb = document.querySelector('meta[property="og:image"]');
    if (metaThumb) {
      thumbnail = metaThumb.content;
    }

    // Get video title
    let title = document.title.replace(' - YouTube', '');
    
    return {
      hasVideo: true,
      paused: video.paused,
      currentTime: video.currentTime,
      duration: video.duration,
      volume: video.volume,
      muted: video.muted,
      thumbnail: thumbnail,
      title: title,
      url: window.location.href
    };
  }

  // Send video state to background
  function sendVideoState() {
    const state = getVideoState();
    chrome.runtime.sendMessage({
      type: 'VIDEO_STATE',
      state: state
    });
  }

  // Listen for commands from popup
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    video = getVideo();
    
    if (!video) {
      sendResponse({ success: false, error: 'No video found' });
      return;
    }

    switch (message.type) {
      case 'PLAY':
        video.play();
        sendResponse({ success: true });
        break;
      
      case 'PAUSE':
        video.pause();
        sendResponse({ success: true });
        break;
      
      case 'TOGGLE_PLAY':
        if (video.paused) {
          video.play();
        } else {
          video.pause();
        }
        sendResponse({ success: true });
        break;
      
      case 'SEEK':
        video.currentTime = message.time;
        sendResponse({ success: true });
        break;
      
      case 'VOLUME':
        video.volume = message.volume;
        sendResponse({ success: true });
        break;
      
      case 'MUTE':
        video.muted = true;
        sendResponse({ success: true });
        break;
      
      case 'UNMUTE':
        video.muted = false;
        sendResponse({ success: true });
        break;
      
      case 'SKIP_FORWARD':
        video.currentTime = Math.min(video.currentTime + 10, video.duration);
        sendResponse({ success: true });
        break;
      
      case 'SKIP_BACKWARD':
        video.currentTime = Math.max(video.currentTime - 10, 0);
        sendResponse({ success: true });
        break;
      
      case 'GET_STATE':
        sendResponse({ success: true, state: getVideoState() });
        break;
      
      default:
        sendResponse({ success: false, error: 'Unknown command' });
    }
    
    return true;
  });

  // Start monitoring video
  function startMonitoring() {
    // Send initial state
    sendVideoState();
    
    // Send updates periodically
    if (updateInterval) {
      clearInterval(updateInterval);
    }
    
    updateInterval = setInterval(() => {
      video = getVideo();
      if (video && !video.paused) {
        sendVideoState();
      }
    }, 1000);

    // Listen for video events
    video = getVideo();
    if (video) {
      video.addEventListener('play', sendVideoState);
      video.addEventListener('pause', sendVideoState);
      video.addEventListener('volumechange', sendVideoState);
      video.addEventListener('seeked', sendVideoState);
    }
  }

  // Initialize when page loads
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', startMonitoring);
  } else {
    startMonitoring();
  }

  // Re-check for video element periodically (for SPAs like YouTube)
  setInterval(() => {
    if (!video || !document.contains(video)) {
      startMonitoring();
    }
  }, 2000);
})();
