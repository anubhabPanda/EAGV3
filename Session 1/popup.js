// Popup script for YouTube Controller
console.log('Popup loaded');

// Get DOM elements
const statusElement = document.getElementById('status');
const nowPlayingElement = document.getElementById('nowPlaying');
const videoThumbnailElement = document.getElementById('videoThumbnail');
const videoTitleElement = document.getElementById('videoTitle');
const videoChannelElement = document.getElementById('videoChannel');
const videoTimeElement = document.getElementById('videoTime');
const playIcon = document.getElementById('playIcon');
const pauseIcon = document.getElementById('pauseIcon');

let currentYouTubeTab = null;
let updateInterval = null;

// Find YouTube tab
async function findYouTubeTab() {
  const tabs = await chrome.tabs.query({ url: ['https://www.youtube.com/watch*', 'https://youtube.com/watch*'] });
  return tabs.length > 0 ? tabs[0] : null;
}

// Send command to YouTube tab
async function sendCommand(action) {
  if (!currentYouTubeTab) {
    currentYouTubeTab = await findYouTubeTab();
    if (!currentYouTubeTab) {
      updateStatus('No YouTube video found', 'error');
      return null;
    }
  }
  
  try {
    const response = await chrome.tabs.sendMessage(currentYouTubeTab.id, { action });
    return response;
  } catch (error) {
    console.error('Error sending command:', error);
    updateStatus('Error: Refresh YouTube page', 'error');
    currentYouTubeTab = null;
    return null;
  }
}

// Update status message
function updateStatus(message, type = 'success') {
  statusElement.textContent = message;
  statusElement.className = `status ${type}`;
}

// Format time (seconds to MM:SS)
function formatTime(seconds) {
  if (!seconds || isNaN(seconds)) return '0:00';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

// Update video info
async function updateVideoInfo() {
  const response = await sendCommand('getPlaybackState');
  
  if (response && response.videoInfo) {
    const { videoInfo, isPlaying, currentTime, duration, volume } = response;
    
    // Show now playing section
    nowPlayingElement.style.display = 'flex';
    
    // Update thumbnail
    if (videoInfo.thumbnail) {
      videoThumbnailElement.src = videoInfo.thumbnail;
    }
    
    // Update title
    if (videoInfo.title) {
      videoTitleElement.textContent = videoInfo.title;
    }
    
    // Update channel
    if (videoInfo.channel) {
      videoChannelElement.textContent = videoInfo.channel;
    }
    
    // Update time
    videoTimeElement.textContent = `${formatTime(currentTime)} / ${formatTime(duration)}`;
    
    // Update play/pause icon
    if (isPlaying) {
      playIcon.style.display = 'none';
      pauseIcon.style.display = 'block';
    } else {
      playIcon.style.display = 'block';
      pauseIcon.style.display = 'none';
    }
    
    updateStatus('Ready', 'success');
  }
}

// Button click handlers
document.getElementById('playPause').addEventListener('click', async () => {
  const response = await sendCommand('playPause');
  if (response) {
    updateStatus(response.status);
    updateVideoInfo();
  }
});

document.getElementById('next').addEventListener('click', async () => {
  const response = await sendCommand('next');
  if (response) {
    updateStatus(response.status);
    setTimeout(updateVideoInfo, 1000);
  }
});

document.getElementById('previous').addEventListener('click', async () => {
  const response = await sendCommand('previous');
  if (response) {
    updateStatus(response.status);
    updateVideoInfo();
  }
});

document.getElementById('volumeUp').addEventListener('click', async () => {
  const response = await sendCommand('volumeUp');
  if (response) {
    updateStatus(response.status);
  }
});

document.getElementById('volumeDown').addEventListener('click', async () => {
  const response = await sendCommand('volumeDown');
  if (response) {
    updateStatus(response.status);
  }
});

document.getElementById('forward').addEventListener('click', async () => {
  const response = await sendCommand('forward');
  if (response) {
    updateStatus(response.status);
    updateVideoInfo();
  }
});

document.getElementById('rewind').addEventListener('click', async () => {
  const response = await sendCommand('rewind');
  if (response) {
    updateStatus(response.status);
    updateVideoInfo();
  }
});

// Initialize
async function init() {
  console.log('Checking YouTube status...');
  
  // Find YouTube tab
  currentYouTubeTab = await findYouTubeTab();
  
  if (currentYouTubeTab) {
    updateStatus('Connecting...');
    await updateVideoInfo();
    
    // Update every 2 seconds
    updateInterval = setInterval(updateVideoInfo, 2000);
  } else {
    updateStatus('No YouTube video found', 'error');
  }
}

// Start
init();

// Clean up on popup close
window.addEventListener('unload', () => {
  if (updateInterval) {
    clearInterval(updateInterval);
  }
});
