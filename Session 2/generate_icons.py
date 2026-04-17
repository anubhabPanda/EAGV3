"""
Generate icons for the Hotel Comparison Chrome extension.
Requires PIL/Pillow: pip install pillow
"""

import os

try:
    from PIL import Image, ImageDraw, ImageFont
    
    # Create icons directory if it doesn't exist
    os.makedirs('icons', exist_ok=True)
    
    def create_icon(size, filename):
        # Create a gradient background (purple/blue)
        img = Image.new('RGB', (size, size), color='#667eea')
        draw = ImageDraw.Draw(img)
        
        # Draw a hotel icon representation
        if size >= 48:
            # For larger icons, draw a stylized hotel building
            margin = size // 5
            
            # Building body (rectangle)
            building_left = margin
            building_right = size - margin
            building_top = margin + 10
            building_bottom = size - margin
            
            draw.rectangle(
                [building_left, building_top, building_right, building_bottom],
                fill='white'
            )
            
            # Windows (small rectangles)
            window_size = max(3, size // 20)
            window_spacing = max(5, size // 15)
            
            for row in range(3):
                for col in range(3):
                    x = building_left + window_spacing + col * window_spacing
                    y = building_top + window_spacing + row * window_spacing
                    draw.rectangle(
                        [x, y, x + window_size, y + window_size],
                        fill='#667eea'
                    )
            
            # Door at the bottom center
            door_width = max(6, size // 12)
            door_height = max(10, size // 8)
            door_x = (size - door_width) // 2
            door_y = building_bottom - door_height
            draw.rectangle(
                [door_x, door_y, door_x + door_width, door_y + door_height],
                fill='#667eea'
            )
            
        else:
            # For small icon (16x16), draw a simple hotel symbol
            draw.rectangle([4, 3, 12, 13], fill='white')
            # Small windows
            draw.rectangle([6, 5, 7, 6], fill='#667eea')
            draw.rectangle([9, 5, 10, 6], fill='#667eea')
            draw.rectangle([6, 8, 7, 9], fill='#667eea')
            draw.rectangle([9, 8, 10, 9], fill='#667eea')
            # Door
            draw.rectangle([7, 11, 9, 13], fill='#667eea')
        
        # Save the image
        img.save(f'icons/{filename}')
        print(f'Created icons/{filename}')
    
    # Generate all three icon sizes
    print('Generating extension icons...')
    create_icon(16, 'icon16.png')
    create_icon(48, 'icon48.png')
    create_icon(128, 'icon128.png')
    
    print('\nAll icons generated successfully!')
    print('You can now load the extension in Chrome.')

except ImportError:
    print('PIL/Pillow is not installed.')
    print('Install it with: pip install pillow')
    print('Or create the icons manually')
except Exception as e:
    print(f'Error generating icons: {e}')
