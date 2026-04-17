# Hotel Comparison Assistant - Chrome Extension

An AI-powered Chrome extension that helps you compare hotels across multiple websites using Google Gemini. Extract hotel details automatically and get intelligent comparisons based on your criteria.

## DEMO LINK

[AI Hotel Comparison](https://youtu.be/KG_mNgNEC3Y)

## 🌟 Features

- **🏨 AI-Powered Extraction**: Automatically extracts hotel information from any website (Booking.com, MakeMyTrip, Hotels.com, etc.)
- **📍 Location-Based Distance**: Calculate distances from your reference location (city center, airport, etc.)
- **🎯 Multi-Hotel Comparison**: Add hotels from different websites and compare them side-by-side
- **🤖 Smart AI Analysis**: Get intelligent comparisons using Google Gemini based on your criteria
- **📱 Dockable Sidebar**: Easy-to-use sidebar interface that doesn't interfere with browsing
- **⚡ Real-time Updates**: Hotels are displayed immediately as you add them

## 📋 Prerequisites

- Python 3.8 or higher
- Google Chrome or any Chromium-based browser
- Google Gemini API Key (get it from [Google AI Studio](https://makersuite.google.com/app/apikey))

## 🚀 Installation

### Step 1: Install Python Dependencies

```bash
cd "Session 2"
pip install flask flask-cors python-dotenv google-genai beautifulsoup4 geopy
pip install pillow  # For generating extension icons
```

### Step 2: Set Up Environment Variables

Create a `.env` file in the `Session 2` folder:

```env
GEMINI_API_KEY=your_gemini_api_key_here
```

### Step 3: Generate Extension Icons

```bash
python generate_icons.py
```

### Step 4: Load Extension in Chrome

1. Open Chrome and navigate to `chrome://extensions/`
2. Enable "Developer mode" (toggle in top-right corner)
3. Click "Load unpacked"
4. Select the `Session 2` folder
5. The extension should now appear in your toolbar

### Step 5: Start the Backend Server

```bash
python server.py
```

The server will start on `http://localhost:5000`

**Important**: Keep the server running while using the extension!

## 📖 How to Use

### 1. Set Your Reference Location

1. Click the extension icon to open the sidebar
2. Enter your reference location in the text box (e.g., "Times Square, New York" or "Airport")
3. This will be used to calculate distances to hotels

### 2. Add Hotels

1. Navigate to any hotel listing website (Booking.com, MakeMyTriip, Hotels.com, etc.)
2. Go to a specific hotel's detail page or listing
3. Click the **"➕ Add Current Hotel"** button in the sidebar
4. Wait for the AI to extract the hotel information (takes 5-10 seconds)
5. The hotel will appear in your list with:
   - Name, location, price, rating
   - Key amenities
   - Main positive and negative reviews
   - Distance from your reference location
   - Hotel image

### 3. Add Multiple Hotels

- Repeat the process on different hotel pages
- You can add hotels from completely different websites
- Mix and match from Booking.com, MakeMyTrip, Expedia, etc.

### 4. Compare Hotels

1. Once you have at least 2 hotels added, the "🔍 Compare Hotels" button will activate
2. Optionally, enter your comparison criteria (e.g., "best for families", "closest to beach", "best value for money")
3. If you leave it empty, the AI will use default criteria
4. Click "🔍 Compare Hotels"
5. Wait for the AI analysis (takes 10-15 seconds)
6. Scroll down to see the detailed comparison with:
   - Strengths and weaknesses of each hotel
   - Best hotel for different traveler types
   - Overall recommendation
   - Final ranking/verdict

### 5. Manage Your List

- **Remove a hotel**: Click the "Remove" button on any hotel card
- **Clear all hotels**: Click the "🗑️ Clear All" button
- **Update location**: Change the reference location anytime to recalculate distances

## 🎯 Supported Websites

The extension works on any hotel website, including:

- ✅ Booking.com
- ✅ MakeMyTrip
- ✅ Hotels.com
- ✅ Expedia
- ✅ Airbnb
- ✅ Agoda
- ✅ TripAdvisor
- ✅ And many more!

The AI is smart enough to extract hotel information from any page structure.

## 🔧 Technical Architecture

### Frontend (Chrome Extension)
- **manifest.json**: Extension configuration (Manifest V3)
- **sidebar.html/css/js**: Dockable sidebar UI
- **content.js**: Extracts page HTML
- **background.js**: Service worker for state management

### Backend (Python Server)
- **server.py**: Flask API server
- **gemini_service.py**: Google Gemini integration
  - Hotel data extraction
  - Multi-hotel comparison
  - Distance calculation using geocoding

### Data Flow
```
User clicks "Add Hotel" 
  → Content script captures page HTML
  → Sent to Flask server
  → Gemini extracts structured data
  → Distance calculated via geocoding
  → Hotel displayed in sidebar

User clicks "Compare"
  → All hotels sent to Flask server
  → Gemini analyzes and compares
  → Comparison displayed in sidebar
```

## 🛠️ Configuration

### Change API Server Port

Edit `server.py`:
```python
app.run(debug=True, port=5000)  # Change port here
```

Then update `sidebar.js`:
```javascript
const API_BASE_URL = 'http://localhost:5000/api';  // Update port
```

### Adjust Token Limits

If extraction fails on very long pages, edit `gemini_service.py`:
```python
if len(text_content) > 8000:  # Increase this limit
    text_content = text_content[:8000]
```

## 🐛 Troubleshooting

### Extension Not Loading
- Make sure you've loaded the `Session 2` folder (not the parent folder)
- Check that all files are present (manifest.json, icons folder, etc.)
- Reload the extension from `chrome://extensions/`

### "Add Hotel" Button Not Working
- **Check server is running**: Make sure `python server.py` is running in a terminal
- **Check console**: Right-click sidebar → Inspect → Console tab for errors
- **CORS issues**: The server has CORS enabled, but check browser console for CORS errors
- **Wrong page**: Make sure you're on an actual hotel listing/detail page

### Hotel Extraction Failed
- **Page too complex**: Some pages have anti-scraping measures
- **JavaScript-heavy sites**: Try waiting for the page to fully load
- **API limits**: Check if you've hit Gemini API rate limits
- **Check API key**: Verify your GEMINI_API_KEY in `.env` file

### Distance Calculation Not Working
- **Invalid location**: Make sure reference location is specific enough (include city/country)
- **Hotel location unclear**: The extracted location might be too vague for geocoding
- **Network issues**: Geocoding requires internet connection

### Comparison Button Disabled
- You need at least 2 hotels to compare
- Check the hotel count - it should show "Added Hotels (2)" or more

### Server Errors

Check the server terminal for error messages:

```bash
# Test server is running
curl http://localhost:5000/api/health

# Should return: {"status":"ok","message":"Hotel Comparison API is running"}
```

### API Key Issues
- Get a new key from [Google AI Studio](https://makersuite.google.com/app/apikey)
- Make sure the key is in `.env` file without quotes
- Restart the server after changing `.env`

## 📊 File Structure

```
Session 2/
├── manifest.json              # Extension manifest (Manifest V3)
├── background.js              # Background service worker
├── content.js                 # Content script for HTML extraction
├── sidebar.html               # Sidebar UI structure
├── sidebar.css                # Sidebar styling
├── sidebar.js                 # Sidebar logic and API calls
├── server.py                  # Flask API server
├── gemini_service.py          # Gemini integration & logic
├── generate_icons.py          # Icon generator script
├── .env                       # Environment variables (create this)
├── icons/                     # Extension icons
│   ├── icon16.png
│   ├── icon48.png
│   └── icon128.png
└── README.md                  # This file
```

## 🔒 Privacy & Security

- **No data storage**: Hotels are only stored in browser memory (cleared on browser close)
- **No tracking**: No analytics or tracking of any kind
- **API security**: Gemini API key is only used server-side
- **HTTPS ready**: Can be configured to use HTTPS for production

## ⚡ Performance Tips

1. **Keep hotels list short**: 5-10 hotels is optimal for comparison
2. **Be specific with criteria**: More specific criteria = better comparisons
3. **Close sidebar when not needed**: Reduces memory usage
4. **Clear hotels regularly**: Use "Clear All" to reset

## 🎨 Customization

### Change Theme Colors

Edit `sidebar.css`:
```css
.header {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); /* Change gradient */
}

.add-hotel-btn {
  background: #667eea; /* Change button color */
}
```

### Modify Extraction Fields

Edit `gemini_service.py` in the `extract_hotel_data` function to add/remove fields from the JSON schema.

### Custom Comparison Prompts

Edit the default criteria in `gemini_service.py`:
```python
criteria_text = "Use these default criteria: [your custom criteria]"
```

## 🚀 Future Enhancements

Possible improvements:
- [ ] Save hotel lists to Chrome storage for persistence
- [ ] Export comparison to PDF
- [ ] Price tracking and alerts
- [ ] Multi-currency support
- [ ] Keyboard shortcuts
- [ ] Dark mode
- [ ] Shared comparison links
- [ ] Integration with booking platforms

## 📝 License

See LICENSE file for details.

## 🤝 Contributing

This is a demo project. Feel free to fork and enhance!

## 📞 Support

For issues:
1. Check the troubleshooting section above
2. Verify server is running and API key is valid
3. Check browser and server console logs
4. Ensure all dependencies are installed

## 🙏 Credits

- Built with Google Gemini AI
- Uses Flask for backend API
- Chrome Extensions Manifest V3
- GeoPy for distance calculations
- BeautifulSoup for HTML parsing

---

**Happy Hotel Hunting! 🏨✨**

