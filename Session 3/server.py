"""
Flask server for AI Character Designer Extension
Handles character creation with Gemini agents and image generation
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from gemini_service import create_character_with_agent, generate_character_image
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
    return jsonify({'status': 'ok', 'message': 'AI Character Designer API is running'})

@app.route('/api/create-character', methods=['POST'])
def create_character():
    """
    Create character using Gemini agent with function calling
    
    Request body:
    {
        "description": "Character description from user"
    }
    
    Response:
    {
        "success": true,
        "character": {
            "attributes": {...},
            "backstory": {...},
            "abilities": {...},
            "appearance": {...},
            "equipment": {...},
            "personality": {...},
            "summary": "..."
        }
    }
    """
    try:
        data = request.get_json()
        
        if not data or 'description' not in data:
            return jsonify({
                'success': False,
                'error': 'Character description is required'
            }), 400
        
        description = data['description']
        
        logger.info(f'Creating character: {description}')
        
        # Use agent to create character
        character_data = create_character_with_agent(description)
        
        if not character_data:
            return jsonify({
                'success': False,
                'error': 'Failed to create character'
            }), 500
        
        logger.info('Character created successfully')
        
        return jsonify({
            'success': True,
            'character': character_data
        })
        
    except Exception as e:
        logger.error(f'Error creating character: {e}', exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/generate-image', methods=['POST'])
def generate_image():
    """
    Generate character image using Gemini image model
    
    Request body:
    {
        "character_data": {complete character data}
    }
    
    Response:
    {
        "success": true,
        "image": "data:image/png;base64,..."
    }
    """
    try:
        data = request.get_json()
        
        if not data or 'character_data' not in data:
            return jsonify({
                'success': False,
                'error': 'Character data is required'
            }), 400
        
        character_data = data['character_data']
        
        logger.info('Generating character image...')
        
        # Generate image
        image_data = generate_character_image(character_data)
        
        if not image_data:
            return jsonify({
                'success': False,
                'error': 'Failed to generate image'
            }), 500
        
        logger.info('Image generated successfully')
        
        return jsonify({
            'success': True,
            'image': image_data
        })
        
    except Exception as e:
        logger.error(f'Error generating image: {e}', exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    logger.info('Starting AI Character Designer API server...')
    logger.info('Server will run on http://localhost:5001')
    logger.info('API endpoints:')
    logger.info('  - POST /api/create-character')
    logger.info('  - POST /api/generate-image')
    logger.info('  - GET /api/health')
    app.run(debug=True, port=5001)
