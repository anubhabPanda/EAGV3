"""
Flask server for Hotel Comparison Chrome Extension
Handles Gemini API calls for hotel data extraction and comparison
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from gemini_service import extract_hotel_data, compare_hotels_gemini, calculate_distance
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for Chrome extension

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'message': 'Hotel Comparison API is running'})

@app.route('/api/extract-hotel', methods=['POST'])
def extract_hotel():
    """
    Extract hotel data from HTML using Gemini
    
    Request body:
    {
        "html": "page HTML content",
        "url": "page URL",
        "location": "reference location (optional)"
    }
    
    Response:
    {
        "success": true,
        "hotel": {
            "name": "Hotel name",
            "price": "Price information",
            "rating": "Rating",
            "location": "Hotel location",
            "amenities": "List of amenities",
            "positiveReviews": "Main positive reviews",
            "negativeReviews": "Main negative reviews",
            "image": "Image URL",
            "distance": "Distance from reference location"
        }
    }
    """
    try:
        data = request.get_json()
        
        if not data or 'html' not in data:
            return jsonify({
                'success': False,
                'error': 'HTML content is required'
            }), 400
        
        html_content = data['html']
        url = data.get('url', '')
        reference_location = data.get('location', '')
        
        logger.info(f'Extracting hotel data from URL: {url}')
        
        # Extract hotel data using Gemini
        hotel_data = extract_hotel_data(html_content, url)
        
        if not hotel_data:
            return jsonify({
                'success': False,
                'error': 'Could not extract hotel data from the page'
            }), 400
        
        # Calculate distance if reference location is provided
        if reference_location and hotel_data.get('location'):
            try:
                logger.info(f'Calculating distance from {hotel_data["location"]} to {reference_location}')
                distance = calculate_distance(
                    hotel_data['location'],
                    reference_location
                )
                if distance:
                    hotel_data['distance'] = distance
                    logger.info(f'Distance calculated: {distance}')
                else:
                    logger.warning('Distance calculation returned None')
                    hotel_data['distance'] = 'Distance unavailable'
            except Exception as e:
                logger.warning(f'Failed to calculate distance: {e}')
                hotel_data['distance'] = 'Distance unavailable'
        else:
            logger.info(f'Skipping distance calculation - Reference: "{reference_location}", Hotel location: "{hotel_data.get("location")}"')
        
        logger.info(f'Successfully extracted hotel: {hotel_data.get("name", "Unknown")}')
        
        return jsonify({
            'success': True,
            'hotel': hotel_data
        })
        
    except Exception as e:
        logger.error(f'Error extracting hotel data: {e}', exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/compare-hotels', methods=['POST'])
def compare_hotels():
    """
    Compare multiple hotels using Gemini
    
    Request body:
    {
        "hotels": [array of hotel objects],
        "criteria": "comparison criteria (optional)"
    }
    
    Response:
    {
        "success": true,
        "comparison": "Comparison text from Gemini"
    }
    """
    try:
        data = request.get_json()
        
        if not data or 'hotels' not in data:
            return jsonify({
                'success': False,
                'error': 'Hotels array is required'
            }), 400
        
        hotels = data['hotels']
        
        if len(hotels) < 2:
            return jsonify({
                'success': False,
                'error': 'At least 2 hotels are required for comparison'
            }), 400
        
        criteria = data.get('criteria', '')
        
        logger.info(f'Comparing {len(hotels)} hotels with criteria: {criteria or "default"}')
        
        # Compare hotels using Gemini
        comparison_result = compare_hotels_gemini(hotels, criteria)
        
        if not comparison_result:
            return jsonify({
                'success': False,
                'error': 'Failed to generate comparison'
            }), 500
        
        logger.info('Successfully generated comparison')
        
        return jsonify({
            'success': True,
            'comparison': comparison_result
        })
        
    except Exception as e:
        logger.error(f'Error comparing hotels: {e}', exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    logger.info('Starting Hotel Comparison API server...')
    logger.info('Server will run on http://localhost:5000')
    logger.info('API endpoints:')
    logger.info('  - POST /api/extract-hotel')
    logger.info('  - POST /api/compare-hotels')
    logger.info('  - GET /api/health')
    app.run(debug=True, port=5000)
