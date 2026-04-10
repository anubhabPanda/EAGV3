"""
Simple script to generate placeholder icons for the Chrome extension.
Requires PIL/Pillow: pip install pillow
"""

try:
    from PIL import Image, ImageDraw, ImageFont
    
    def create_icon(size, filename):
        # Create a red background
        img = Image.new('RGB', (size, size), color='#FF0000')
        draw = ImageDraw.Draw(img)
        
        # Draw a white play triangle
        if size >= 48:
            # For larger icons, draw a play triangle
            margin = size // 4
            points = [
                (margin, margin),
                (margin, size - margin),
                (size - margin, size // 2)
            ]
            draw.polygon(points, fill='white')
        else:
            # For small icon, draw a white circle with play symbol
            draw.ellipse([4, 4, size-4, size-4], fill='white')
            mini_points = [
                (7, 5),
                (7, size-5),
                (size-5, size // 2)
            ]
            draw.polygon(mini_points, fill='#FF0000')
        
        # Save the image
        img.save(f'icons/{filename}')
        print(f'Created icons/{filename}')
    
    # Generate all three icon sizes
    create_icon(16, 'icon16.png')
    create_icon(48, 'icon48.png')
    create_icon(128, 'icon128.png')
    
    print('\nAll icons generated successfully!')
    print('You can now load the extension in Chrome.')

except ImportError:
    print('PIL/Pillow is not installed.')
    print('Install it with: pip install pillow')
    print('Or create the icons manually (see icons/README.md)')
