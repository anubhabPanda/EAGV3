// Popup script to control YouTube playback
let currentState = null;
let isDraggingProgress = false;

// DOM Elements
const noVideoDiv = document.getElementById('no-video');
const videoControlsDiv = document.getElementById('video-controls');
const thumbnail = document.getElementById('thumbnail');
const videoTitle = document.getElementById('video-title');
const playPauseBtn = document.getElementById('play-pause');
const playIcon = document.getElementById('play-icon');
const pauseIcon = document.getElementById('pause-icon');
const skipBackBtn = document.getElementById('skip-back');
const skipForwardBtn = document.getElementById('skip-forward');
const progressBar = document.getElementById('progress-bar');
const currentTimeSpan = document.getElementById('current-time');
const durationSpan = document.getElementById('duration');
const muteBtn = document.getElementById('mute-btn');
const volumeIcon = document.getElementById('volume-icon');
const muteIcon = document.getElementById('mute-icon');
const volumeSlider = document.getElementById('volume-slider');
const volumeUpBtn = document.getElementById('volume-up');
const volumeDownBtn = document.getElementById('volume-down');
const prevVideoBtn = document.getElementById('prev-video');
const nextVideoBtn = document.getElementById('next-video');
const openVideoBtn = document.getElementById('open-video');

// Format time in seconds to MM:SS
function formatTime(seconds) {
  if (!seconds || isNaN(seconds)) return '0:00';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

// Send command to background
function sendCommand(command) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage({
      type: 'SEND_COMMAND',
      command: command
    }, (response) => {
      resolve(response);
    });
  });
}

// Update UI with current state
function updateUI(state) {
  currentState = state;
  
  if (!state.hasVideo) {
    noVideoDiv.style.display = 'flex';
    videoControlsDiv.style.display = 'none';
    return;
  }
  
  noVideoDiv.style.display = 'none';
  videoControlsDiv.style.display = 'block';
  
  // Update thumbnail and title
  if (state.thumbnail) {
    thumbnail.src = state.thumbnail;
  }
  videoTitle.textContent = state.title || 'YouTube Video';
  
  // Update play/pause button
  if (state.paused) {
    playIcon.style.display = 'block';
    pauseIcon.style.display = 'none';
  } else {
    playIcon.style.display = 'none';
    pauseIcon.style.display = 'block';
  }
  
  // Update progress bar
  if (!isDraggingProgress) {
    const progress = (state.currentTime / state.duration) * 100 || 0;
    progressBar.value = progress;
    currentTimeSpan.textContent = formatTime(state.currentTime);
    durationSpan.textContent = formatTime(state.duration);
  }
  
  // Update volume
  volumeSlider.value = state.volume * 100;
  if (state.muted || state.volume === 0) {
    volumeIcon.style.display = 'none';
    muteIcon.style.display = 'block';
  } else {
    volumeIcon.style.display = 'block';
    muteIcon.style.display = 'none';
  }
}

// Get current state from background
function refreshState() {
  chrome.runtime.sendMessage({ type: 'GET_CURRENT_STATE' }, (response) => {
    if (response && response.state) {
      updateUI(response.state);
    }
  });
}

// Event Listeners
playPauseBtn.addEventListener('click', async () => {
  await sendCommand({ type: 'TOGGLE_PLAY' });
  setTimeout(refreshState, 100);
});

skipBackBtn.addEventListener('click', async () => {
  await sendCommand({ type: 'SKIP_BACKWARD' });
  setTimeout(refreshState, 100);
});

skipForwardBtn.addEventListener('click', async () => {
  await sendCommand({ type: 'SKIP_FORWARD' });
  setTimeout(refreshState, 100);
});

progressBar.addEventListener('mousedown', () => {
  isDraggingProgress = true;
});

progressBar.addEventListener('mouseup', async () => {
  isDraggingProgress = false;
  if (currentState && currentState.duration) {
    const newTime = (progressBar.value / 100) * currentState.duration;
    await sendCommand({ type: 'SEEK', time: newTime });
    setTimeout(refreshState, 100);
  }
});

progressBar.addEventListener('input', () => {
  if (currentState && currentState.duration) {
    const newTime = (progressBar.value / 100) * currentState.duration;
    currentTimeSpan.textContent = formatTime(newTime);
  }
});

muteBtn.addEventListener('click', async () => {
  if (currentState.muted) {
    await sendCommand({ type: 'UNMUTE' });
  } else {
    await sendCommand({ type: 'MUTE' });
  }
  setTimeout(refreshState, 100);
});

volumeSlider.addEventListener('input', async () => {
  const volume = volumeSlider.value / 100;
  await sendCommand({ type: 'VOLUME', volume: volume });
  setTimeout(refreshState, 100);
});

volumeUpBtn.addEventListener('click', async () => {
  if (currentState) {
    const newVolume = Math.min(currentState.volume + 0.1, 1);
    await sendCommand({ type: 'VOLUME', volume: newVolume });
    setTimeout(refreshState, 100);
  }
});

volumeDownBtn.addEventListener('click', async () => {
  if (currentState) {
    const newVolume = Math.max(currentState.volume - 0.1, 0);
    await sendCommand({ type: 'VOLUME', volume: newVolume });
    setTimeout(refreshState, 100);
  }
});

prevVideoBtn.addEventListener('click', async () => {
  await sendCommand({ type: 'PREV_VIDEO' });
  setTimeout(refreshState, 500);
});

nextVideoBtn.addEventListener('click', async () => {
  await sendCommand({ type: 'NEXT_VIDEO' });
  setTimeout(refreshState, 500);
});

openVideoBtn.addEventListener('click', () => {
  if (currentState && currentState.url) {
    chrome.tabs.create({ url: currentState.url });
  }
});

// Initialize and refresh periodically
refreshState();
setInterval(refreshState, 1000);
