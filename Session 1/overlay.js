// YouTube Controller Overlay Script
console.log('YouTube Controller Overlay: Initializing...');

(function() {
  'use strict';

  let overlayElement = null;
  let updateInterval = null;
  let isVisible = false;

  // Check if we're on a YouTube page
  const isYouTubePage = window.location.hostname.includes('youtube.com');

  // Inject CSS if not already injected
  function injectCSS() {
    const cssId = 'yt-controller-overlay-css';
    if (document.getElementById(cssId)) return;

    const link = document.createElement('link');
    link.id = cssId;
    link.rel = 'stylesheet';
    link.href = chrome.runtime.getURL('overlay.css');
    document.head.appendChild(link);
  }

  // Create overlay UI
  function createOverlay() {
    if (overlayElement) return;

    // Inject CSS first
    injectCSS();

    // Load HTML template
    fetch(chrome.runtime.getURL('overlay.html'))
      .then(response => response.text())
      .then(html => {
        // Create container
        const container = document.createElement('div');
        container.innerHTML = html;
        overlayElement = container.firstElementChild;

        // Add to page
        document.body.appendChild(overlayElement);

        // Attach event listeners
        attachEventListeners();

        // Start updating if on YouTube
        if (isYouTubePage) {
          startUpdating();
        }

        isVisible = true;
        console.log('YouTube Controller Overlay: Created and visible');
      })
      .catch(err => {
        console.error('YouTube Controller Overlay: Failed to load', err);
      });
  }

  // Remove overlay
  function removeOverlay() {
    if (overlayElement) {
      overlayElement.classList.add('yt-hidden');
      setTimeout(() => {
        if (overlayElement && overlayElement.parentNode) {
          overlayElement.parentNode.removeChild(overlayElement);
        }
        overlayElement = null;
      }, 300);
    }
    stopUpdating();
    isVisible = false;
  }

  // Toggle overlay visibility
  function toggleOverlay() {
    if (isVisible) {
      removeOverlay();
    } else {
      createOverlay();
    }
  }

  // Find YouTube tab and send command
  async function sendCommandToYouTube(action) {
    try {
      const tabs = await chrome.tabs.query({ url: 'https://www.youtube.com/watch*' });

      if (tabs.length === 0) {
        console.log('No YouTube tab found');
        return null;
      }

      // Send to first YouTube tab
      return new Promise((resolve) => {
        chrome.runtime.sendMessage({
          action: 'sendToTab',
          tabId: tabs[0].id,
          command: action
        }, (response) => {
          resolve(response);
        });
      });
    } catch (error) {
      console.error('Error sending command to YouTube:', error);
      return null;
    }
  }

  // Get video player (works on any page with YouTube embed or YouTube itself)
  function getVideoPlayer() {
    // Try YouTube page video
    let video = document.querySelector('video.html5-main-video');
    if (video) return video;

    // Try any video element
    video = document.querySelector('video');
    return video;
  }

  // Format time
  function formatTime(seconds) {
    if (!seconds || isNaN(seconds)) return '0:00';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  }

  // Update video info
  function updateVideoInfo() {
    if (!overlayElement || !isVisible) return;

    const video = getVideoPlayer();
    if (!video) {
      updateNoVideo();
      return;
    }

    // Update play/pause icon
    const playIcon = overlayElement.querySelector('#yt-play-icon');
    const pauseIcon = overlayElement.querySelector('#yt-pause-icon');
    if (video.paused) {
      playIcon.style.display = 'block';
      pauseIcon.style.display = 'none';
    } else {
      playIcon.style.display = 'none';
      pauseIcon.style.display = 'block';
    }

    // Update time
    const timeDisplay = overlayElement.querySelector('#yt-time-display');
    if (timeDisplay) {
      timeDisplay.textContent = `${formatTime(video.currentTime)} / ${formatTime(video.duration)}`;
    }

    // Update volume
    const volumeFill = overlayElement.querySelector('#yt-volume-fill');
    if (volumeFill) {
      volumeFill.style.width = `${video.volume * 100}%`;
    }

    // Update video info if on YouTube
    if (isYouTubePage) {
      updateYouTubeInfo();
    }
  }

  // Update with "No Video" state
  function updateNoVideo() {
    const title = overlayElement.querySelector('#yt-video-title');
    const channel = overlayElement.querySelector('#yt-video-channel');
    const thumbnail = overlayElement.querySelector('#yt-thumbnail');
    const timeDisplay = overlayElement.querySelector('#yt-time-display');

    if (title) title.textContent = 'No video playing';
    if (channel) channel.textContent = 'YouTube Controller';
    if (thumbnail) thumbnail.style.display = 'none';
    if (timeDisplay) timeDisplay.textContent = '0:00 / 0:00';
  }

  // Update YouTube-specific info
  function updateYouTubeInfo() {
    const title = overlayElement.querySelector('#yt-video-title');
    const channel = overlayElement.querySelector('#yt-video-channel');
    const thumbnail = overlayElement.querySelector('#yt-thumbnail');

    // Get title
    const titleSelectors = [
      'h1.ytd-watch-metadata yt-formatted-string',
      'h1.title yt-formatted-string',
      'h1 yt-formatted-string.ytd-watch-metadata'
    ];

    for (const selector of titleSelectors) {
      const titleElement = document.querySelector(selector);
      if (titleElement && titleElement.textContent) {
        if (title) title.textContent = titleElement.textContent.trim();
        break;
      }
    }

    // Get channel
    const channelSelectors = [
      'ytd-channel-name yt-formatted-string a',
      'ytd-channel-name a'
    ];

    for (const selector of channelSelectors) {
      const channelElement = document.querySelector(selector);
      if (channelElement && channelElement.textContent) {
        if (channel) channel.textContent = channelElement.textContent.trim();
        break;
      }
    }

    // Get thumbnail
    const videoId = new URLSearchParams(window.location.search).get('v');
    if (videoId && thumbnail) {
      thumbnail.src = `https://i.ytimg.com/vi/${videoId}/default.jpg`;
      thumbnail.style.display = 'block';
    }
  }

  // Attach event listeners to buttons
  function attachEventListeners() {
    if (!overlayElement) return;

    const playPauseBtn = overlayElement.querySelector('#yt-btn-play-pause');
    const previousBtn = overlayElement.querySelector('#yt-btn-previous');
    const nextBtn = overlayElement.querySelector('#yt-btn-next');
    const volumeUpBtn = overlayElement.querySelector('#yt-btn-volume-up');
    const volumeDownBtn = overlayElement.querySelector('#yt-btn-volume-down');
    const forwardBtn = overlayElement.querySelector('#yt-btn-forward');
    const rewindBtn = overlayElement.querySelector('#yt-btn-rewind');
    const closeBtn = overlayElement.querySelector('#yt-btn-close');

    if (playPauseBtn) playPauseBtn.addEventListener('click', handlePlayPause);
    if (previousBtn) previousBtn.addEventListener('click', handlePrevious);
    if (nextBtn) nextBtn.addEventListener('click', handleNext);
    if (volumeUpBtn) volumeUpBtn.addEventListener('click', handleVolumeUp);
    if (volumeDownBtn) volumeDownBtn.addEventListener('click', handleVolumeDown);
    if (forwardBtn) forwardBtn.addEventListener('click', handleForward);
    if (rewindBtn) rewindBtn.addEventListener('click', handleRewind);
    if (closeBtn) closeBtn.addEventListener('click', removeOverlay);
  }

  // Send command to YouTube tab via background script
  async function sendCommandToYouTube(action) {
    try {
      const response = await chrome.runtime.sendMessage({
        action: 'controlYouTube',
        command: action
      });

      if (response && response.success) {
        return response;
      } else {
        console.log('YouTube control failed:', response);
        return null;
      }
    } catch (error) {
      console.error('Error sending command to YouTube:', error);
      return null;
    }
  }

  // Control handlers - Try local video first, then YouTube tab
  async function handlePlayPause() {
    const video = getVideoPlayer();

    // If on YouTube page, control local video
    if (video && isYouTubePage) {
      if (video.paused) {
        video.play();
      } else {
        video.pause();
      }
      updateVideoInfo();
      return;
    }

    // Otherwise, send command to YouTube tab
    const response = await sendCommandToYouTube('playPause');
    if (response && response.videoInfo) {
      updateNowPlaying(response.videoInfo);
      updatePlayPauseIcon(response.isPlaying);
    }
  }

  async function handlePrevious() {
    const video = getVideoPlayer();

    // If on YouTube page, control local video
    if (video && isYouTubePage) {
      if (video.currentTime > 3) {
        video.currentTime = 0;
      } else {
        const prevButton = document.querySelector('.ytp-prev-button');
        if (prevButton) prevButton.click();
      }
      updateVideoInfo();
      return;
    }

    // Otherwise, send command to YouTube tab
    await sendCommandToYouTube('previous');
    setTimeout(updateVideoInfoFromYouTube, 500);
  }

  async function handleNext() {
    const video = getVideoPlayer();

    // If on YouTube page, control local video
    if (video && isYouTubePage) {
      const nextButton = document.querySelector('.ytp-next-button');
      if (nextButton) nextButton.click();
      setTimeout(updateVideoInfo, 1000);
      return;
    }

    // Otherwise, send command to YouTube tab
    await sendCommandToYouTube('next');
    setTimeout(updateVideoInfoFromYouTube, 1000);
  }

  async function handleVolumeUp() {
    const video = getVideoPlayer();

    // If on YouTube page, control local video
    if (video && isYouTubePage) {
      video.volume = Math.min(1, video.volume + 0.1);
      updateVideoInfo();
      return;
    }

    // Otherwise, send command to YouTube tab
    const response = await sendCommandToYouTube('volumeUp');
    if (response && response.videoInfo) {
      updateNowPlaying(response.videoInfo);
    }
  }

  async function handleVolumeDown() {
    const video = getVideoPlayer();

    // If on YouTube page, control local video
    if (video && isYouTubePage) {
      video.volume = Math.max(0, video.volume - 0.1);
      updateVideoInfo();
      return;
    }

    // Otherwise, send command to YouTube tab
    const response = await sendCommandToYouTube('volumeDown');
    if (response && response.videoInfo) {
      updateNowPlaying(response.videoInfo);
    }
  }

  async function handleForward() {
    const video = getVideoPlayer();

    // If on YouTube page, control local video
    if (video && isYouTubePage) {
      video.currentTime = Math.min(video.duration, video.currentTime + 10);
      updateVideoInfo();
      return;
    }

    // Otherwise, send command to YouTube tab
    await sendCommandToYouTube('forward');
    setTimeout(updateVideoInfoFromYouTube, 200);
  }

  async function handleRewind() {
    const video = getVideoPlayer();

    // If on YouTube page, control local video
    if (video && isYouTubePage) {
      video.currentTime = Math.max(0, video.currentTime - 10);
      updateVideoInfo();
      return;
    }

    // Otherwise, send command to YouTube tab
    await sendCommandToYouTube('rewind');
    setTimeout(updateVideoInfoFromYouTube, 200);
  }

  // Update video info from YouTube tab
  async function updateVideoInfoFromYouTube() {
    const response = await sendCommandToYouTube('getVideoInfo');
    if (response && response.videoInfo) {
      updateNowPlaying(response.videoInfo);
      if (response.isPlaying !== undefined) {
        updatePlayPauseIcon(response.isPlaying);
      }
    }
  }

  // Update play/pause icon
  function updatePlayPauseIcon(isPlaying) {
    if (!overlayElement) return;

    const playIcon = overlayElement.querySelector('#yt-play-icon');
    const pauseIcon = overlayElement.querySelector('#yt-pause-icon');

    if (isPlaying) {
      if (playIcon) playIcon.style.display = 'none';
      if (pauseIcon) pauseIcon.style.display = 'block';
    } else {
      if (playIcon) playIcon.style.display = 'block';
      if (pauseIcon) pauseIcon.style.display = 'none';
    }
  }

  // Start/stop updating
  function startUpdating() {
    if (updateInterval) return;

    // If on YouTube, update local video
    if (isYouTubePage) {
      updateInterval = setInterval(updateVideoInfo, 1000);
      updateVideoInfo(); // Initial update
    } else {
      // If on other page, get info from YouTube tab
      updateInterval = setInterval(updateVideoInfoFromYouTube, 2000);
      updateVideoInfoFromYouTube(); // Initial update
    }
  }

  function stopUpdating() {
    if (updateInterval) {
      clearInterval(updateInterval);
      updateInterval = null;
    }
  }

  // Keyboard shortcut: Ctrl+Shift+Y
  document.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.shiftKey && e.key === 'Y') {
      e.preventDefault();
      toggleOverlay();
    }
  });

  // Listen for messages from extension
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'toggleOverlay') {
      toggleOverlay();
      sendResponse({ success: true, visible: isVisible });
    } else if (request.action === 'ping') {
      sendResponse({ pong: true, loaded: true });
    }
    return true;
  });

  // Auto-show on YouTube pages
  if (isYouTubePage && window.location.pathname.includes('/watch')) {
    // Wait for page to load
    setTimeout(() => {
      createOverlay();
    }, 2000);
  }

  console.log('YouTube Controller Overlay: Ready (Press Ctrl+Shift+Y to toggle)');
})();
