// Content script for YouTube control
console.log('YouTube Controller: Content script loaded');

// Wait for video player to be available
function waitForVideo(maxAttempts = 50) {
  return new Promise((resolve, reject) => {
    let attempts = 0;
    const checkInterval = setInterval(() => {
      const video = document.querySelector('video');
      if (video) {
        clearInterval(checkInterval);
        resolve(video);
      } else if (++attempts >= maxAttempts) {
        clearInterval(checkInterval);
        reject(new Error('Video player not found'));
      }
    }, 100);
  });
}

// Get the YouTube video player
function getVideoPlayer() {
  return document.querySelector('video');
}

// Get YouTube player controls
function getPlayerButton(selector) {
  return document.querySelector(selector);
}

// Get current video info
function getVideoInfo() {
  const video = getVideoPlayer();
  if (!video) return null;

  // Try multiple selectors for video title
  let title = 'Unknown';
  const titleSelectors = [
    'h1.ytd-watch-metadata yt-formatted-string',
    'h1.title yt-formatted-string',
    'h1 yt-formatted-string.ytd-watch-metadata',
    'yt-formatted-string.style-scope.ytd-watch-metadata'
  ];

  for (const selector of titleSelectors) {
    const titleElement = document.querySelector(selector);
    if (titleElement && titleElement.textContent) {
      title = titleElement.textContent.trim();
      break;
    }
  }

  // Get thumbnail
  let thumbnail = '';
  const thumbnailElement = document.querySelector('link[rel="image_src"]');
  if (thumbnailElement) {
    thumbnail = thumbnailElement.href;
  } else {
    // Fallback: extract video ID and construct thumbnail URL
    const videoId = new URLSearchParams(window.location.search).get('v');
    if (videoId) {
      thumbnail = `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg`;
    }
  }

  // Get channel name
  let channel = 'Unknown';
  const channelSelectors = [
    'ytd-channel-name yt-formatted-string a',
    'ytd-channel-name a',
    '#channel-name a'
  ];

  for (const selector of channelSelectors) {
    const channelElement = document.querySelector(selector);
    if (channelElement && channelElement.textContent) {
      channel = channelElement.textContent.trim();
      break;
    }
  }

  return {
    title,
    channel,
    thumbnail,
    duration: video.duration,
    currentTime: video.currentTime,
    isPlaying: !video.paused,
    volume: Math.round(video.volume * 100)
  };
}

// Handle playback commands
function handlePlayPause() {
  const video = getVideoPlayer();
  if (!video) return { status: 'No video found', isPlaying: false };

  if (video.paused) {
    video.play();
    return { status: 'Playing', isPlaying: true };
  } else {
    video.pause();
    return { status: 'Paused', isPlaying: false };
  }
}

function handleNext() {
  const nextButton = getPlayerButton('.ytp-next-button');
  if (nextButton) {
    nextButton.click();
    // Wait a bit for new video to load
    setTimeout(() => {
      const videoInfo = getVideoInfo();
      if (videoInfo) {
        chrome.runtime.sendMessage({ action: 'videoChanged', videoInfo });
      }
    }, 1000);
    return { status: 'Next video' };
  }
  return { status: 'Next button not found' };
}

function handlePrevious() {
  const video = getVideoPlayer();
  if (!video) return { status: 'No video found' };

  // If more than 3 seconds in, restart video. Otherwise try to go to previous
  if (video.currentTime > 3) {
    video.currentTime = 0;
    return { status: 'Restarted video' };
  } else {
    const prevButton = getPlayerButton('.ytp-prev-button');
    if (prevButton) {
      prevButton.click();
      // Wait a bit for new video to load
      setTimeout(() => {
        const videoInfo = getVideoInfo();
        if (videoInfo) {
          chrome.runtime.sendMessage({ action: 'videoChanged', videoInfo });
        }
      }, 1000);
      return { status: 'Previous video' };
    }
    video.currentTime = 0;
    return { status: 'Restarted video' };
  }
}

function handleVolumeUp() {
  const video = getVideoPlayer();
  if (!video) return { status: 'No video found' };

  const newVolume = Math.min(1, video.volume + 0.1);
  video.volume = newVolume;
  return { status: `Volume: ${Math.round(newVolume * 100)}%` };
}

function handleVolumeDown() {
  const video = getVideoPlayer();
  if (!video) return { status: 'No video found' };

  const newVolume = Math.max(0, video.volume - 0.1);
  video.volume = newVolume;
  return { status: `Volume: ${Math.round(newVolume * 100)}%` };
}

function handleForward() {
  const video = getVideoPlayer();
  if (!video) return { status: 'No video found' };

  video.currentTime = Math.min(video.duration, video.currentTime + 10);
  return { status: 'Forward 10s' };
}

function handleRewind() {
  const video = getVideoPlayer();
  if (!video) return { status: 'No video found' };

  video.currentTime = Math.max(0, video.currentTime - 10);
  return { status: 'Rewind 10s' };
}

function getPlaybackState() {
  const video = getVideoPlayer();
  if (!video) return { isPlaying: false, videoInfo: null };

  const videoInfo = getVideoInfo();
  return {
    isPlaying: !video.paused,
    videoInfo: videoInfo
  };
}

// Listen for messages from popup or other tabs (via background)
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  console.log('Content script received message:', request);

  // Handle ping immediately
  if (request.action === 'ping') {
    sendResponse({ pong: true });
    return false;
  }

  let response;

  try {
    switch (request.action) {
      case 'playPause':
        response = handlePlayPause();
        break;
      case 'next':
        response = handleNext();
        break;
      case 'previous':
        response = handlePrevious();
        break;
      case 'volumeUp':
        response = handleVolumeUp();
        break;
      case 'volumeDown':
        response = handleVolumeDown();
        break;
      case 'forward':
        response = handleForward();
        break;
      case 'rewind':
        response = handleRewind();
        break;
      case 'getPlaybackState':
        response = getPlaybackState();
        break;
      case 'getVideoInfo':
        const videoInfo = getVideoInfo();
        const video = getVideoPlayer();
        response = {
          videoInfo: videoInfo,
          isPlaying: video ? !video.paused : false
        };
        break;
      default:
        response = { status: 'Unknown command' };
    }
  } catch (error) {
    console.error('Error handling command:', error);
    response = { status: 'Error: ' + error.message };
  }

  console.log('Sending response:', response);

  // Send response immediately and synchronously
  try {
    sendResponse(response);
  } catch (e) {
    console.error('Error sending response:', e);
  }

  return false; // Synchronous response
});

// Notify that content script is ready
console.log('YouTube Controller: Ready to receive commands');

// Wait for video and send initial state
waitForVideo().then(() => {
  console.log('YouTube Controller: Video player detected');
}).catch(err => {
  console.log('YouTube Controller: No video player found yet');
});
