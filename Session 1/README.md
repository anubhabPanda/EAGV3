# Youtube Controller - Chrome Extension

A Chrome extension that lets you control YouTube playback from any tab with a beautiful control panel featuring video preview and all standard YouTube controls.

## Features

- 🎬 **Video Preview** - See the thumbnail and title of the currently playing video
- ⏯️ **Playback Controls** - Play, pause, skip forward/backward (10 seconds)
- 📊 **Progress Bar** - Seek to any position in the video
- 🔊 **Volume Control** - Adjust volume and mute/unmute
- 🚀 **Universal Access** - Control YouTube from ANY Chrome tab or window
- 🎯 **Auto-Detection** - Automatically detects when YouTube videos are playing
- 🔴 **Status Indicator** - Shows a badge when a video is active

## Installation

### Option 1: Load Unpacked Extension (Development)

1. **Generate Icons** (required):
   ```bash
   # If you have Python and pip installed:
   pip install pillow
   python generate_icons.py
   ```
   
   Or create icons manually (see `icons/README.md`)

2. **Open Chrome Extensions Page**:
   - Navigate to `chrome://extensions/`
   - Or click the three dots menu → More Tools → Extensions

3. **Enable Developer Mode**:
   - Toggle the "Developer mode" switch in the top-right corner

4. **Load the Extension**:
   - Click "Load unpacked"
   - Select the extension folder (where `manifest.json` is located)

5. **Pin the Extension** (optional):
   - Click the extensions icon (puzzle piece) in the toolbar
   - Find "Youtube Controller" and click the pin icon

### Option 2: Package as .crx (For Distribution)

1. On the `chrome://extensions/` page, click "Pack extension"
2. Select the extension directory
3. Click "Pack Extension"
4. Share the generated `.crx` file

## Usage

1. **Play a YouTube Video**:
   - Open any YouTube video in any tab
   - The extension will automatically detect it

2. **Open the Control Panel**:
   - Click the extension icon in your toolbar
   - You'll see the video preview and controls

3. **Control Playback**:
   - **Play/Pause**: Click the large center button
   - **Skip**: Use the -10s and +10s buttons
   - **Seek**: Drag the progress bar
   - **Volume**: Adjust the volume slider or click mute
   - **Open Tab**: Click "Open Video Tab" to switch to the YouTube tab

4. **Works Everywhere**:
   - Browse other websites while your video plays
   - Control YouTube without switching tabs
   - The extension tracks the active video automatically

## File Structure

```
youtube-controller/
├── manifest.json          # Extension configuration
├── background.js          # Background service worker
├── content.js            # Script injected into YouTube pages
├── popup.html            # Control panel UI
├── popup.js              # Control panel logic
├── popup.css             # Control panel styling
├── generate_icons.py     # Icon generator script
├── icons/
│   ├── icon16.png       # 16x16 icon
│   ├── icon48.png       # 48x48 icon
│   ├── icon128.png      # 128x128 icon
│   └── README.md        # Icon generation guide
└── EXTENSION_README.md   # This file
```

## How It Works

1. **Content Script** (`content.js`):
   - Runs on all YouTube pages
   - Detects video elements
   - Sends video state to background script
   - Receives and executes control commands

2. **Background Service Worker** (`background.js`):
   - Maintains connection between YouTube tabs and popup
   - Stores current video state
   - Routes commands from popup to active YouTube tab
   - Updates extension badge

3. **Popup Interface** (`popup.html/js/css`):
   - Displays current video information
   - Provides control interface
   - Sends user commands to background script
   - Updates UI in real-time

## Browser Compatibility

- ✅ Google Chrome (Manifest V3)
- ✅ Microsoft Edge (Chromium-based)
- ✅ Brave Browser
- ✅ Other Chromium-based browsers

## Permissions Explained

- **tabs**: Access to tab information to find YouTube tabs
- **scripting**: Inject content scripts into YouTube pages
- **storage**: Store extension state (if needed in future)
- **host_permissions (*.youtube.com)**: Access YouTube pages to control playback

## Troubleshooting

### Extension icon shows no badge
- Make sure a YouTube video is actually playing
- Try refreshing the YouTube tab
- Check if the extension is enabled

### Controls not working
- Verify the YouTube tab is still open
- Refresh the YouTube page
- Reload the extension from `chrome://extensions/`

### No video preview showing
- Some videos may not have thumbnails immediately
- The title should still be visible
- Controls will work regardless of thumbnail

## Future Enhancements

Possible features to add:
- Keyboard shortcuts
- Multiple video management
- Picture-in-picture support
- Playlist controls
- Speed control
- Mini-player mode
- Dark/light theme toggle

## Contributing

Feel free to modify and enhance this extension! Some ideas:
- Add more controls (quality, captions, speed)
- Improve UI/UX
- Add keyboard shortcuts
- Support for other video platforms
- Better error handling

## License

See LICENSE file for details.

## Credits

Created as a YouTube playback control extension for Chrome.
