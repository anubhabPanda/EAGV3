"""
Gemini Service for Hotel Data Extraction and Comparison
Uses Google Gemini API to analyze hotel listings and compare options
"""

from google import genai
import os
import json
import re
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from geopy.geocoders import Nominatim
from geopy.distance import geodesic

# Load environment variables
load_dotenv()

# Initialize Gemini client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = "gemini-3.1-flash-lite-preview"

# Initialize geocoder for distance calculation with better user agent
geolocator = Nominatim(
    user_agent="hotel_comparison_extension_v1.0 (contact: user@example.com)",
    timeout=10
)


def extract_hotel_image(soup, url):
    """
    Extract the main hotel image from the page

    Args:
        soup: BeautifulSoup object of the page
        url: URL of the page

    Returns:
        str: Image URL or None
    """
    try:
        # Strategy 1: Look for Open Graph image (most reliable)
        og_image = soup.find('meta', property='og:image')
        if og_image and og_image.get('content'):
            image_url = og_image['content']
            print(f"Found OG image: {image_url}")
            return image_url

        # Strategy 2: Look for Twitter card image
        twitter_image = soup.find('meta', attrs={'name': 'twitter:image'})
        if twitter_image and twitter_image.get('content'):
            image_url = twitter_image['content']
            print(f"Found Twitter image: {image_url}")
            return image_url

        # Strategy 3: Look for large images in the page
        # Find all img tags with common hotel image patterns
        images = soup.find_all('img')
        for img in images:
            src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
            if not src:
                continue

            # Skip small images (icons, buttons, etc.)
            width = img.get('width')
            height = img.get('height')
            if width and height:
                try:
                    if int(width) < 200 or int(height) < 150:
                        continue
                except:
                    pass

            # Skip common non-hotel images
            if any(skip in src.lower() for skip in ['logo', 'icon', 'avatar', 'profile', 'banner', 'ad']):
                continue

            # Check if it's a likely hotel image
            if any(keyword in src.lower() for keyword in ['hotel', 'room', 'property', 'photo', 'image', 'gallery']):
                # Make URL absolute if it's relative
                if src.startswith('//'):
                    image_url = 'https:' + src
                elif src.startswith('/'):
                    from urllib.parse import urljoin
                    image_url = urljoin(url, src)
                else:
                    image_url = src

                print(f"Found hotel image from img tag: {image_url}")
                return image_url

        # Strategy 4: Just get the first reasonably sized image
        for img in images[:10]:  # Check first 10 images
            src = img.get('src') or img.get('data-src')
            if src and len(src) > 20:  # URL should be reasonably long
                if src.startswith('//'):
                    image_url = 'https:' + src
                elif src.startswith('/'):
                    from urllib.parse import urljoin
                    image_url = urljoin(url, src)
                else:
                    image_url = src

                print(f"Using first available image: {image_url}")
                return image_url

        print("No suitable image found")
        return None

    except Exception as e:
        print(f"Error extracting hotel image: {e}")
        return None


def extract_hotel_data(html_content, url=""):
    """
    Extract hotel data from HTML using Gemini

    Args:
        html_content: Full HTML of the hotel listing page
        url: URL of the page (for context)

    Returns:
        dict: Extracted hotel information
    """
    try:
        # Clean HTML to reduce token count (remove scripts, styles, etc.)
        soup = BeautifulSoup(html_content, 'html.parser')

        # Extract image URL before cleaning
        image_url = extract_hotel_image(soup, url)
        print(f"Extracted image URL: {image_url}")

        # Remove script and style elements
        for script in soup(["script", "style", "noscript", "iframe"]):
            script.decompose()

        # Get text content
        text_content = soup.get_text(separator='\n', strip=True)

        # Limit text length to avoid token limits (approx 8000 chars)
        if len(text_content) > 8000:
            text_content = text_content[:8000]

        # Create prompt for Gemini
        prompt = f"""
You are a hotel data extraction assistant. Analyze the following webpage content from a hotel listing and extract relevant information.

URL: {url}

Page Content:
{text_content}

Extract the following information in JSON format:
{{
    "name": "Hotel name",
    "price": "Price per night (include currency)",
    "rating": "Rating (e.g., 4.5/5 or 4.5 stars)",
    "location": "Hotel location/address",
    "amenities": "Key amenities (WiFi, Pool, Gym, etc.) - summarize in one line",
    "positiveReviews": "Main positive points from reviews (2-3 key points)",
    "negativeReviews": "Main negative points from reviews (2-3 key points)"
}}

Rules:
1. Extract only factual information from the page
2. If a field is not found, use "Not available"
3. Be concise and accurate
4. For reviews, summarize the main themes
5. Return ONLY valid JSON, no additional text

JSON Response:
"""

        # Call Gemini API
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt
        )

        # Parse JSON from response
        response_text = response.text.strip()

        # Extract JSON from response (in case there's extra text)
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            hotel_data = json.loads(json_match.group())
        else:
            hotel_data = json.loads(response_text)

        # Add the extracted image URL
        if image_url:
            hotel_data['image'] = image_url
        else:
            hotel_data['image'] = None

        return hotel_data

    except Exception as e:
        print(f"Error extracting hotel data: {e}")
        return None


def compare_hotels_gemini(hotels, criteria=""):
    """
    Compare multiple hotels using Gemini

    Args:
        hotels: List of hotel dictionaries
        criteria: User-specified comparison criteria (optional)

    Returns:
        str: Comparison summary from Gemini
    """
    try:
        # Prepare hotel data for comparison
        hotels_summary = []
        for i, hotel in enumerate(hotels, 1):
            summary = f"""
Hotel {i}: {hotel.get('name', 'Unknown')}
- Price: {hotel.get('price', 'N/A')}
- Rating: {hotel.get('rating', 'N/A')}
- Location: {hotel.get('location', 'N/A')}
- Distance: {hotel.get('distance', 'N/A')}
- Amenities: {hotel.get('amenities', 'N/A')}
- Positive Reviews: {hotel.get('positiveReviews', 'N/A')}
- Negative Reviews: {hotel.get('negativeReviews', 'N/A')}
"""
            hotels_summary.append(summary)

        # Create comparison prompt
        if criteria:
            criteria_text = f"User's specific criteria: {criteria}"
        else:
            criteria_text = "Use these default criteria: overall value for money, location convenience, amenities, and guest satisfaction"

        prompt = f"""
You are a hotel comparison expert. Compare the following hotels and provide a CONCISE analysis.

{chr(10).join(hotels_summary)}

{criteria_text}

Provide a BRIEF comparison (max 300 words) with these sections:

### Quick Overview
Brief 1-sentence summary of each hotel

### Top Recommendation
Which hotel wins based on the criteria and why (2-3 sentences)

### Final Ranking
Rank hotels with brief reasoning

FORMATTING RULES:
- Use ### for section headers
- Use **bold** for hotel names when first mentioned
- Use bullet points (-) for lists
- Be concise and direct
- Keep total under 300 words
- Use emojis sparingly: 🏆 💰 📍 ⭐ 👨‍👩‍👧‍👦 💼

DO NOT use HTML tags, only use markdown (###, **, -)
"""

        # Call Gemini API
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt
        )

        return response.text.strip()

    except Exception as e:
        print(f"Error comparing hotels: {e}")
        return None


def calculate_distance(hotel_location, reference_location):
    """
    Calculate distance between hotel and reference location using geocoding
    If geocoding fails, use Gemini to estimate the distance

    Args:
        hotel_location: Hotel address/location
        reference_location: Reference point (e.g., city center, airport)

    Returns:
        str: Distance in km (e.g., "2.5 km from city center")
    """
    try:
        import time

        # Check if we have valid inputs
        if not hotel_location or not reference_location:
            print(f"Missing location data - Hotel: '{hotel_location}', Reference: '{reference_location}'")
            return None

        print(f"Calculating distance from '{hotel_location}' to '{reference_location}'")

        # Try geocoding approach first
        try:
            # Geocode reference location first (more likely to succeed)
            time.sleep(1.5)  # Rate limiting - Nominatim requires min 1 sec between requests
            ref_coords = geolocator.geocode(reference_location, timeout=10)

            if not ref_coords:
                print(f"Failed to geocode reference location: '{reference_location}', trying AI estimation...")
                return estimate_distance_with_ai(hotel_location, reference_location)

            print(f"Reference location geocoded: {ref_coords.latitude}, {ref_coords.longitude}")

            # Geocode hotel location
            time.sleep(1.5)  # Rate limiting
            hotel_coords = geolocator.geocode(hotel_location, timeout=10)

            if not hotel_coords:
                print(f"Failed to geocode hotel location: '{hotel_location}', trying AI estimation...")
                return estimate_distance_with_ai(hotel_location, reference_location)

            print(f"Hotel location geocoded: {hotel_coords.latitude}, {hotel_coords.longitude}")

            # Calculate distance
            distance_km = geodesic(
                (hotel_coords.latitude, hotel_coords.longitude),
                (ref_coords.latitude, ref_coords.longitude)
            ).kilometers

            print(f"Distance calculated: {distance_km:.2f} km")

            # Format result
            if distance_km < 1:
                return f"{int(distance_km * 1000)} meters from {reference_location}"
            else:
                return f"{distance_km:.1f} km from {reference_location}"

        except Exception as e:
            print(f"Geocoding error: {e}, trying AI estimation...")
            return estimate_distance_with_ai(hotel_location, reference_location)

    except Exception as e:
        print(f"Error calculating distance: {e}")
        import traceback
        traceback.print_exc()
        return None


def estimate_distance_with_ai(hotel_location, reference_location):
    """
    Use Gemini AI to estimate distance when geocoding fails
    """
    try:
        print(f"Using AI to estimate distance from '{hotel_location}' to '{reference_location}'")

        prompt = f"""
Estimate the approximate distance between these two locations:

Hotel Location: {hotel_location}
Reference Point: {reference_location}

Provide ONLY a concise distance estimate in this format:
"X.X km from [reference location]" or "XXX meters from [reference location]"

If you cannot estimate, respond with: "Distance unavailable"

Be brief and factual. Examples:
- "2.5 km from ooty bus stand"
- "500 meters from city center"
- "Distance unavailable"
"""

        response = client.models.generate_content(
            model=MODEL,
            contents=prompt
        )

        distance_text = response.text.strip()
        print(f"AI estimated distance: {distance_text}")

        # Clean up the response
        if "unavailable" in distance_text.lower():
            return None

        return distance_text

    except Exception as e:
        print(f"Error in AI distance estimation: {e}")
        return None


# Test function (can be removed in production)
if __name__ == "__main__":
    print("Gemini Service for Hotel Comparison")
    print("Testing Gemini connection...")

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents="Say 'Hello from Gemini!' if you can hear me."
        )
        print("Connection successful!")
        print("Response:", response.text)
    except Exception as e:
        print("Connection failed:", e)