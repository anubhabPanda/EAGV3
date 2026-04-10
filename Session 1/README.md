# 🎵 YouTube Controller - Chrome Extension

Control YouTube playback from **ANY tab** with a simple popup interface!

**Key Features:**
- 🌐 Control YouTube from any tab (Gmail, Reddit, anywhere!)
- 🎨 Beautiful gradient popup design
- 🎵 See what's playing with thumbnail and info
- ⚡ Simple and reliable - just click the icon!
- 🔄 Auto-updates video info every 2 seconds

## ✨ New in Version 2.0

- 🍎 **Apple-Style Design** - Beautiful glassmorphism with blur and transparency
- 📍 **Floating Bar** - Docked at top of screen, always accessible
- ⌨️ **Keyboard Shortcut** - Press `Ctrl+Shift+Y` to show/hide instantly
- 🌐 **Works Everywhere** - Control videos on ANY webpage, not just YouTube
- 🎬 **Auto-Show** - Automatically appears on YouTube video pages
- ✨ **Smooth Animations** - Slide in/out with Apple-style easing

## Features

- 🎵 **Now Playing** - See current video title, channel, and thumbnail
- ⏱️ **Progress Display** - View current time and duration
- 🎚️ **Visual Volume Bar** - See volume level at a glance
- ▶️ **Play/Pause** - Toggle video playback
- ⏭️ **Next** - Skip to next video
- ⏮️ **Previous** - Go to previous video (or restart current video)
- 🔊 **Volume Up/Down** - Adjust volume in 10% increments
- ⏩ **Fast Forward** - Jump forward 10 seconds
- ⏪ **Rewind** - Jump back 10 seconds
- 🎨 **Beautiful UI** - Apple-inspired glassmorphism design
- 🚀 **Works from any tab** - Control YouTube even when working elsewhere
- 🔄 **Auto-Update** - Live playback state and video info updates

## 🚀 Installation (2 Minutes)

### Step 1: Load Extension
1. Open Chrome: `chrome://extensions/`
2. Enable **Developer mode** (top-right toggle)
3. Click **Load unpacked**
4. Select this folder
5. Extension loads! ✅

### Step 2: Reload & Test
1. Click reload button ⟳ on the extension
2. Open new tab → Go to `https://www.youtube.com`
3. Press `Ctrl+Shift+Y` (or `Cmd+Shift+Y` on Mac)
4. Beautiful bar appears! 🎉

---

## ⚠️ Important Notes

### Where It Works
- ✅ **Works:** Regular websites (YouTube, Google, Reddit, etc.)
- ❌ **Doesn't Work:** Chrome internal pages (`chrome://extensions/`, `chrome://settings/`)

**Why?** Chrome security blocks extensions on internal pages.

### Common First-Time Issue
**Error:** "Could not establish connection"

**Cause:** Trying to use on a `chrome://` page

**Solution:**
1. Open a regular website (youtube.com)
2. Press `Ctrl+Shift+Y`
3. Works perfectly! ✅

## 🎮 How to Use

### Control YouTube from ANY Tab (Main Feature!)

**Example: Control YouTube while checking email**

1. **Tab 1:** Open YouTube → Play a video
2. **Tab 2:** Open Gmail (or any website)
3. **In Tab 2:** Press `Ctrl+Shift+Y`
4. **Result:** Bar appears showing YouTube video info
5. **Click controls:** YouTube responds instantly! ✅

### Three Ways to Toggle the Bar

1. **Keyboard Shortcut** (Recommended)
   - Press: `Ctrl+Shift+Y` (Windows/Linux)
   - Press: `Cmd+Shift+Y` (Mac)

2. **Extension Icon**
   - Click the icon in your toolbar

3. **Auto-show**
   - Opens automatically on YouTube video pages after 2 seconds
   - Click X to close

### Controls Available

- ▶/⏸ **Play/Pause** - Toggle playback
- ⏭ **Next** - Skip to next video
- ⏮ **Previous** - Go to previous/restart
- ⏩ **Forward** - Jump ahead 10 seconds
- ⏪ **Rewind** - Jump back 10 seconds
- 🔊 **Volume Up** - Increase volume
- 🔉 **Volume Down** - Decrease volume
- ✕ **Close** - Hide the bar

## 🐛 Troubleshooting

### Bar Doesn't Appear
1. Reload extension: `chrome://extensions/` → Click ⟳
2. Refresh your page (F5)
3. Press `Ctrl+Shift+Y`
4. Make sure you're on a regular website (not chrome://)

### Controls Don't Work from Other Tabs
1. Make sure YouTube tab is open with a video (`/watch?v=`)
2. Reload extension
3. Refresh both YouTube tab and your current tab
4. Try again

### No Video Info Shown
1. Wait 2-3 seconds (updates every 2 seconds)
2. Make sure YouTube video is playing
3. Check console (F12) for errors

---

## 📁 File Structure

```
youtube-controller/
├── manifest.json       # Extension configuration
├── background.js       # Message routing between tabs
├── content.js          # YouTube video controller
├── overlay.js          # Floating bar logic
├── overlay.css         # Apple-style design
├── overlay.html        # Bar UI structure
├── icon*.png           # Extension icons
├── README.md           # This file
└── Documentation files (.md, .txt)
```

## 🔧 How It Works

### Architecture

**When on YouTube Tab:**
```
Overlay → Directly controls video → Instant response
```

**When on Other Tabs:**
```
Your Tab → Background Script → YouTube Tab → Response back
```

### Components

1. **overlay.js** - Floating bar UI on all pages
2. **background.js** - Routes messages between tabs
3. **content.js** - Controls YouTube video player
4. **overlay.css** - Apple-style glassmorphism design

---

## 💡 Pro Tips

- **Pin YouTube tab**: Right-click → Pin tab (keeps it always open)
- **Multiple YouTube tabs**: Extension controls the first video tab it finds
- **Best performance**: Keep YouTube tab loaded, not suspended
- **Customize shortcut**: Go to `chrome://extensions/shortcuts`

---

## 🎨 Customization

### Change Transparency
Edit `overlay.css` line 23:
```css
background: rgba(255, 255, 255, 0.7);  /* Change 0.7 to 0.5-0.9 */
```

### Move Bar Position
Edit `overlay.css` lines 4-6:
```css
top: 20px;    /* Distance from top */
left: 50%;    /* Keep centered */
```

### Disable Auto-Show
Edit `overlay.js` lines 432-437, comment out the auto-show code.

---

## 🌐 Browser Compatibility

- ✅ Google Chrome
- ✅ Microsoft Edge
- ✅ Brave
- ✅ Other Chromium browsers

---

## 🔒 Privacy

- ✅ No data collection
- ✅ No external servers
- ✅ Runs entirely locally
- ✅ Open source - see the code!

---

## 📝 License

Free to use and modify for personal use.

---

## 🎉 Quick Summary

1. **Install**: Load unpacked from `chrome://extensions/`
2. **Open**: YouTube video in one tab
3. **Switch**: To any other tab
4. **Press**: `Ctrl+Shift+Y`
5. **Control**: YouTube from anywhere! 🎵

**Need help?** Check the troubleshooting section above or read `WHERE-IT-WORKS.md`.

Enjoy your beautiful Apple-style YouTube controller! 🍎✨
