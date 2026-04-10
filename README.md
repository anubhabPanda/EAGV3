# 🎵 YouTube Controller - Chrome Extension

Control YouTube playback from **ANY tab** with a beautiful Apple-style floating overlay!

![Version](https://img.shields.io/badge/version-2.0-blue)
![Chrome](https://img.shields.io/badge/chrome-extension-green)
![License](https://img.shields.io/badge/license-MIT-orange)

## ✨ Key Features

- 🌐 **Universal Control** - Control YouTube from any tab (Gmail, Reddit, anywhere!)
- 🎨 **Apple-Style Design** - Beautiful glassmorphism floating bar with blur effects
- 🎵 **Rich Info Display** - See video thumbnail, title, channel, and playback time
- ⌨️ **Keyboard Shortcut** - Quick toggle with `Ctrl+Shift+Y` (or `Cmd+Shift+Y` on Mac)
- ⚡ **Dual Interface** - Floating overlay AND popup interface
- 🔄 **Real-time Updates** - Auto-updates video info every 2 seconds
- 🎯 **Smart Control** - Direct control on YouTube, cross-tab control everywhere else

## 🚀 Quick Start

### Installation (3 Steps)

1. **Open Chrome Extensions**
   ```
   chrome://extensions/
   ```

2. **Enable Developer Mode**
   - Toggle switch in top-right corner

3. **Load Extension**
   - Click "Load unpacked"
   - Select the `Session 1` folder
   - Done! ✅

### First Use

1. Open YouTube and play a video
2. Switch to any other tab (e.g., google.com)
3. Press `Ctrl+Shift+Y` or click the extension icon
4. Enjoy your floating control bar! 🎉

## 🎮 How to Use

### Floating Overlay (Recommended)

Press `Ctrl+Shift+Y` (or `Cmd+Shift+Y` on Mac) on any tab to show/hide the floating control bar.

**Features:**
- Docks at the top of your screen
- Shows video thumbnail, title, and channel
- Full playback controls (play/pause, next, previous, seek, volume)
- Real-time progress display
- Transparent glassmorphism design

### Popup Interface

Click the extension icon in your Chrome toolbar for a compact popup with:
- Video thumbnail and info
- Playback controls
- Status indicator

## 🎛️ Controls

| Control | Action | Shortcut |
|---------|--------|----------|
| ▶/⏸ | Play/Pause | - |
| ⏮ | Previous video / Restart | - |
| ⏭ | Next video | - |
| ⏪ | Rewind 10 seconds | - |
| ⏩ | Forward 10 seconds | - |
| 🔉 | Volume down | - |
| 🔊 | Volume up | - |
| ✕ | Close overlay | `Ctrl+Shift+Y` |

## 🏗️ Architecture

### Component Overview

```
youtube-controller/
├── manifest.json       # Extension configuration (Manifest V3)
├── background.js       # Service worker for message routing
├── content.js          # YouTube video player controller
├── overlay.js          # Floating bar logic and cross-tab control
├── overlay.css         # Apple-style glassmorphism design
├── overlay.html        # Floating bar UI structure
├── popup.js            # Popup interface logic
├── popup.css           # Popup styling
├── popup.html          # Popup UI structure
└── icon*.png           # Extension icons (16, 48, 128)
```

### How It Works

**On YouTube Tab:**
```
Overlay → Direct Video Control → Instant Response
```

**On Other Tabs:**
```
Your Tab → Background Service Worker → YouTube Tab → Response Back
```

### Technical Details

1. **overlay.js** - Injected on all pages, creates floating bar UI, handles control logic
2. **background.js** - Service worker that routes messages between tabs
3. **content.js** - Runs only on YouTube, provides direct access to video player
4. **Cross-tab Communication** - Uses Chrome message passing API for seamless control

## 🌍 Compatibility

### ✅ Works On
- YouTube (direct control)
- All regular websites (https://, http://)
- Gmail, Google Docs, Drive
- Reddit, Twitter, Facebook
- Any web page you can browse

### ❌ Doesn't Work On
- `chrome://` pages (extensions, settings, etc.)
- `edge://` pages
- Local file (`file://`) pages

**Why?** Chrome security policies block extensions on internal pages.

## 🐛 Troubleshooting

### "Could not establish connection" Error

**Cause:** You're on a `chrome://` page where extensions can't run.

**Fix:** Open any regular website and try again.

### Overlay Doesn't Appear

1. Go to `chrome://extensions/`
2. Click reload (⟳) on YouTube Controller
3. Refresh your current tab (F5)
4. Press `Ctrl+Shift+Y`
5. Ensure you're not on a `chrome://` page

### Controls Don't Work from Other Tabs

**Requirements:**
- YouTube tab must be open with a video (`/watch?v=` URL)
- Video must be loaded

**Fix:**
1. Verify YouTube tab is open and playing
2. Reload extension at `chrome://extensions/`
3. Refresh both YouTube tab and current tab
4. Try again

### No Video Info Displayed

**Wait:** Info updates automatically every 2 seconds.

**Check:**
1. YouTube video is actually playing
2. YouTube tab is open and loaded
3. Open DevTools (F12) → Console for error messages

## 💡 Pro Tips

1. **Pin YouTube Tab** - Right-click → "Pin tab" to keep it always available
2. **Multiple YouTube Tabs** - Extension controls the first video tab it finds
3. **Leave Overlay Visible** - Keep it open while working for easy access
4. **Customize Shortcut** - Go to `chrome://extensions/shortcuts` to change keybinding
5. **Best Performance** - Keep YouTube tab loaded (not suspended/discarded)

## 🎨 Customization

### Adjust Transparency

Edit `overlay.css` around line 23:
```css
background: rgba(255, 255, 255, 0.7);  /* Change 0.7 to 0.5-0.9 */
```
- Higher value (0.9) = More solid
- Lower value (0.5) = More transparent

### Change Position

Edit `overlay.css` around line 5:
```css
top: 20px;  /* Lower number = higher on screen */
```

### Modify Blur Effect

Edit `overlay.css`:
```css
backdrop-filter: blur(10px);  /* Increase for more blur */
```

## 📚 Documentation

For more detailed information, see the `Session 1` folder:

- **START-HERE.txt** - Quick overview and welcome guide
- **USER-GUIDE.md** - Complete installation and usage guide
- **WHERE-IT-WORKS.md** - Compatible pages explained
- **CROSS-TAB-CONTROL.md** - Technical details on cross-tab communication

## 🔧 Development

### Tech Stack
- Manifest V3
- Vanilla JavaScript (no frameworks)
- Chrome Extension APIs (tabs, runtime, messaging)
- CSS3 (glassmorphism, backdrop-filter)

### Key APIs Used
- `chrome.runtime.sendMessage()` - Message passing
- `chrome.tabs.query()` - Tab detection
- `chrome.commands.onCommand` - Keyboard shortcuts
- Content Scripts - Page interaction
- Service Workers - Background processing

## 📝 License

This project is open source and available under the MIT License.

## 🤝 Contributing

Contributions are welcome! Feel free to:
- Report bugs
- Suggest features
- Submit pull requests

## 💬 Support

If you encounter issues:
1. Check the troubleshooting section above
2. Review the documentation in `Session 1` folder
3. Open an issue on GitHub

## 🎯 Use Cases

### Working
- Tab 1: YouTube music playlist
- Tab 2: Google Docs
- Control music while writing without switching tabs

### Email
- Tab 1: YouTube tutorial
- Tab 2: Gmail
- Pause tutorial when emails arrive

### Browsing
- Tab 1: YouTube podcast
- Tab 2: Reddit/Twitter
- Browse while listening, control playback anytime

---

**Enjoy controlling YouTube from anywhere! 🎵**

Made with ❤️ for productivity and music lovers
