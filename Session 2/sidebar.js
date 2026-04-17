// Sidebar JavaScript for Hotel Comparison Extension

// API Configuration
const API_BASE_URL = 'http://localhost:5000/api';

// State
let hotels = [];
let userLocation = '';

// DOM Elements
const locationInput = document.getElementById('location-input');
const addHotelBtn = document.getElementById('add-hotel-btn');
const clearAllBtn = document.getElementById('clear-all-btn');
const hotelsList = document.getElementById('hotels-list');
const hotelCount = document.getElementById('hotel-count');
const criteriaInput = document.getElementById('criteria-input');
const compareBtn = document.getElementById('compare-btn');
const comparisonResults = document.getElementById('comparison-results');
const comparisonContent = document.getElementById('comparison-content');
const loading = document.getElementById('loading');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  loadHotels();
  loadLocation();
});

// Load hotels from background
async function loadHotels() {
  const response = await chrome.runtime.sendMessage({ type: 'GET_HOTELS' });
  if (response) {
    hotels = response.hotels || [];
    userLocation = response.location || '';
    locationInput.value = userLocation;
    console.log('Loaded hotels from background:', hotels.length, 'hotels');
    renderHotels();
  }
}

// Save location to background
function saveLocation() {
  userLocation = locationInput.value;
  chrome.runtime.sendMessage({ type: 'UPDATE_LOCATION', location: userLocation });
}

// Load location
function loadLocation() {
  chrome.runtime.sendMessage({ type: 'GET_HOTELS' }, (response) => {
    if (response && response.location) {
      userLocation = response.location;
      locationInput.value = userLocation;
    }
  });
}

// Render hotels list
function renderHotels() {
  console.log('=== RENDERING HOTELS ===');
  console.log('Hotels array:', hotels);
  console.log('Hotels count:', hotels.length);

  hotelCount.textContent = hotels.length;
  compareBtn.disabled = hotels.length < 2;

  if (hotels.length === 0) {
    hotelsList.innerHTML = `
      <div class="empty-state">
        <p>No hotels added yet</p>
        <small>Browse hotel listings and click "Add Current Hotel"</small>
      </div>
    `;
    return;
  }

  hotelsList.innerHTML = hotels.map((hotel, index) => {
    console.log(`Creating card for hotel ${index}:`, hotel.name);
    return createHotelCard(hotel, index);
  }).join('');

  // Add remove button listeners
  document.querySelectorAll('.remove-hotel-btn').forEach((btn, index) => {
    btn.addEventListener('click', () => removeHotel(index));
  });

  console.log('Rendered', hotels.length, 'hotel cards');
}

// Create hotel card HTML
function createHotelCard(hotel, index) {
  const imageUrl = hotel.image || 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="80" height="80"%3E%3Crect fill="%23ddd" width="80" height="80"/%3E%3Ctext x="50%25" y="50%25" text-anchor="middle" dy=".3em" fill="%23999" font-size="30"%3E🏨%3C/text%3E%3C/svg%3E';
  
  return `
    <div class="hotel-card">
      <div class="hotel-header">
        <img src="${imageUrl}" alt="${hotel.name}" class="hotel-image" onerror="this.src='data:image/svg+xml,%3Csvg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'80\\' height=\\'80\\'%3E%3Crect fill=\\'%23ddd\\' width=\\'80\\' height=\\'80\\'/%3E%3Ctext x=\\'50%25\\' y=\\'50%25\\' text-anchor=\\'middle\\' dy=\\'.3em\\' fill=\\'%23999\\' font-size=\\'30\\'%3E🏨%3C/text%3E%3C/svg%3E'">
        <div class="hotel-main-info">
          <div class="hotel-name">${hotel.name || 'Unknown Hotel'}</div>
          <div class="hotel-location">📍 ${hotel.location || 'Location not specified'}</div>
          <div class="hotel-price">💰 ${hotel.price || 'Price not available'}</div>
          <div class="hotel-rating">⭐ ${hotel.rating || 'No rating'}</div>
        </div>
      </div>
      <div class="hotel-details">
        ${hotel.amenities ? `<div class="hotel-amenities"><strong>Amenities:</strong> ${hotel.amenities}</div>` : ''}
        ${hotel.distance ? `<div class="hotel-distance">📏 ${hotel.distance}</div>` : ''}
        ${hotel.positiveReviews ? `<div class="hotel-reviews">👍 <strong>Positive:</strong> ${hotel.positiveReviews}</div>` : ''}
        ${hotel.negativeReviews ? `<div class="hotel-reviews">👎 <strong>Negative:</strong> ${hotel.negativeReviews}</div>` : ''}
      </div>
      <div class="hotel-actions">
        <button class="remove-hotel-btn" data-index="${index}">Remove</button>
      </div>
    </div>
  `;
}

// Add hotel from current page
async function addHotel() {
  try {
    console.log('=== ADDING HOTEL ===');
    loading.style.display = 'block';
    addHotelBtn.disabled = true;

    // Get page HTML from content script
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    console.log('Current tab:', tab.url);

    const response = await chrome.tabs.sendMessage(tab.id, { type: 'GET_PAGE_HTML' });
    console.log('Got page HTML response:', response?.success);

    if (!response || !response.success) {
      throw new Error('Failed to get page data');
    }

    // Send to backend for extraction
    console.log('Sending to backend for extraction...');
    const extractResponse = await fetch(`${API_BASE_URL}/extract-hotel`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        html: response.pageData.html,
        url: response.pageData.url,
        location: userLocation
      })
    });

    if (!extractResponse.ok) {
      throw new Error('Failed to extract hotel data');
    }

    const hotelData = await extractResponse.json();
    console.log('Extracted hotel data:', hotelData);

    if (hotelData.success) {
      console.log('Hotel extracted:', hotelData.hotel.name);
      console.log('Current hotels count BEFORE adding:', hotels.length);

      // Add to background state
      const addResponse = await chrome.runtime.sendMessage({ type: 'ADD_HOTEL', hotel: hotelData.hotel });
      console.log('Add response from background:', addResponse);

      // Reload hotels from background to ensure sync
      if (addResponse && addResponse.success) {
        console.log('Reloading hotels from background...');
        await loadHotels();
        console.log('Current hotels count AFTER reload:', hotels.length);
        showNotification('Hotel added successfully!', 'success');
      }
    } else {
      throw new Error(hotelData.error || 'Failed to extract hotel data');
    }
  } catch (error) {
    console.error('Error adding hotel:', error);
    showNotification('Error: ' + error.message, 'error');
  } finally {
    loading.style.display = 'none';
    addHotelBtn.disabled = false;
  }
}

// Remove hotel
async function removeHotel(index) {
  const response = await chrome.runtime.sendMessage({ type: 'REMOVE_HOTEL', index: index });
  if (response && response.success) {
    hotels = response.hotels;
    renderHotels();
    comparisonResults.style.display = 'none';
    showNotification('Hotel removed', 'success');
  }
}

// Clear all hotels
async function clearAllHotels() {
  if (hotels.length === 0) return;

  if (confirm('Are you sure you want to clear all hotels?')) {
    const response = await chrome.runtime.sendMessage({ type: 'CLEAR_HOTELS' });
    if (response && response.success) {
      hotels = [];
      renderHotels();
      comparisonResults.style.display = 'none';
      showNotification('All hotels cleared', 'success');
    }
  }
}

// Format comparison text with HTML styling
function formatComparisonText(text) {
  // First, clean up the text by removing HTML artifacts
  text = text.replace(/&quot;/g, '"')
            .replace(/&amp;/g, '&')
            .replace(/&lt;/g, '<')
            .replace(/&gt;/g, '>');

  // Convert markdown to HTML
  let formatted = text
    .split('\n')
    .map(line => {
      const trimmed = line.trim();
      if (!trimmed) return '<br>';

      // Handle markdown headers (### Header or ## Header)
      if (trimmed.startsWith('###')) {
        const headerText = trimmed.replace(/^###\s*/, '');
        return `<h3 style="color: #667eea; margin-top: 16px; margin-bottom: 8px; font-size: 15px; font-weight: 700; border-bottom: 2px solid #667eea; padding-bottom: 4px;">${headerText}</h3>`;
      }
      if (trimmed.startsWith('##')) {
        const headerText = trimmed.replace(/^##\s*/, '');
        return `<h2 style="color: #667eea; margin-top: 18px; margin-bottom: 10px; font-size: 16px; font-weight: 700; border-bottom: 2px solid #667eea; padding-bottom: 6px;">${headerText}</h2>`;
      }
      if (trimmed.startsWith('#')) {
        const headerText = trimmed.replace(/^#\s*/, '');
        return `<h1 style="color: #667eea; margin-top: 20px; margin-bottom: 12px; font-size: 18px; font-weight: 700; border-bottom: 2px solid #667eea; padding-bottom: 6px;">${headerText}</h1>`;
      }

      // Handle markdown bold **text**
      let processed = trimmed.replace(/\*\*(.*?)\*\*/g, '<strong style="color: #667eea; font-weight: 600;">$1</strong>');

      // Handle markdown italic *text*
      processed = processed.replace(/\*(.*?)\*/g, '<em>$1</em>');

      // Style numbered lists
      if (/^\d+\./.test(processed)) {
        return `<div style="margin-left: 20px; margin-bottom: 8px; color: #333; line-height: 1.6;">${processed}</div>`;
      }

      // Style bullet points (lines starting with -, *, or •)
      if (/^[-•]/.test(processed)) {
        const content = processed.substring(1).trim();
        return `<div style="margin-left: 20px; margin-bottom: 8px; color: #555; line-height: 1.6;">• ${content}</div>`;
      }

      // Hotel patterns like "Hotel 1:" or "**Hotel 1:**"
      processed = processed.replace(/(Hotel \d+:)/g, '<strong style="color: #667eea; font-weight: 700;">$1</strong>');

      // Dollar amounts
      processed = processed.replace(/(\$\d+)/g, '<span style="color: #10b981; font-weight: 600;">$1</span>');

      // Regular paragraphs
      return `<p style="margin-bottom: 10px; color: #333; line-height: 1.7;">${processed}</p>`;
    })
    .join('');

  // Highlight emojis and make them larger
  formatted = formatted.replace(/(🏆|💰|📍|⭐|👨‍👩‍👧‍👦|💼|✨|🎯|👍|👎|⭐)/g, '<span style="font-size: 18px; margin-right: 4px;">$1</span>');

  // Highlight rankings (#1, #2, etc.) but not markdown headers
  formatted = formatted.replace(/(?<!<h[123].*?)#(\d+)/g, '<strong style="color: #10b981; font-weight: 700; font-size: 14px;">#$1</strong>');

  return formatted;
}

// Compare hotels
async function compareHotels() {
  if (hotels.length < 2) {
    showNotification('Add at least 2 hotels to compare', 'error');
    return;
  }

  try {
    loading.style.display = 'block';
    compareBtn.disabled = true;

    const criteria = criteriaInput.value.trim();

    const response = await fetch(`${API_BASE_URL}/compare-hotels`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        hotels: hotels,
        criteria: criteria || null
      })
    });

    if (!response.ok) {
      throw new Error('Failed to compare hotels');
    }

    const result = await response.json();

    if (result.success) {
      // Format the comparison text for better display
      const formattedComparison = formatComparisonText(result.comparison);
      comparisonContent.innerHTML = formattedComparison;
      comparisonResults.style.display = 'block';

      // Scroll comparison into view smoothly
      setTimeout(() => {
        comparisonResults.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }, 100);
    } else {
      throw new Error(result.error || 'Comparison failed');
    }
  } catch (error) {
    console.error('Error comparing hotels:', error);
    showNotification('Error: ' + error.message, 'error');
  } finally {
    loading.style.display = 'none';
    compareBtn.disabled = false;
  }
}

// Show notification
function showNotification(message, type = 'info') {
  // Simple alert for now - could be enhanced with toast notifications
  const emoji = type === 'success' ? '✅' : type === 'error' ? '❌' : 'ℹ️';
  alert(`${emoji} ${message}`);
}

// Event Listeners
locationInput.addEventListener('blur', saveLocation);
locationInput.addEventListener('change', saveLocation);
addHotelBtn.addEventListener('click', addHotel);
clearAllBtn.addEventListener('click', clearAllHotels);
compareBtn.addEventListener('click', compareHotels);

// Listen for hotel added messages from background
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'HOTEL_ADDED') {
    loadHotels();
  }
});
