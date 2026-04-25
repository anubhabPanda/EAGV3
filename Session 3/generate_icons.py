"""
Generate icons for AI Character Designer Chrome Extension
"""

from PIL import Image, ImageDraw, ImageFont
import os

def create_icon(size):
    """Create a single icon of specified size"""
    # Create image with gradient background
    img = Image.new('RGB', (size, size), color='#667eea')
    draw = ImageDraw.Draw(img)
    
    # Draw gradient effect
    for i in range(size):
        color_value = int(102 + (118 - 102) * (i / size))  # Gradient from #667eea to #764ba2
        draw.line([(0, i), (size, i)], fill=(color_value, 126, 234))
    
    # Add emoji or text
    emoji = "🎮"
    
    try:
        # Try to use a font that supports emoji
        font_size = int(size * 0.6)
        # Use default font
        font = ImageFont.load_default()
    except:
        font = None
    
    # Draw emoji/text
    text = emoji
    
    # Calculate text position (center)
    if font:
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
    else:
        text_width = size // 2
        text_height = size // 2
    
    x = (size - text_width) // 2
    y = (size - text_height) // 2
    
    # Draw white background circle
    circle_radius = int(size * 0.4)
    draw.ellipse(
        [(size//2 - circle_radius, size//2 - circle_radius),
         (size//2 + circle_radius, size//2 + circle_radius)],
        fill='white'
    )
    
    # Draw text
    draw.text((x, y), text, font=font, fill='#667eea')
    
    return img

def main():
    """Generate all icon sizes"""
    sizes = [16, 48, 128]
    
    # Create icons directory if it doesn't exist
    os.makedirs('icons', exist_ok=True)
    
    for size in sizes:
        print(f'Generating {size}x{size} icon...')
        icon = create_icon(size)
        icon.save(f'icons/icon{size}.png')
        print(f'✓ Saved icons/icon{size}.png')
    
    print('\n✅ All icons generated successfully!')

if __name__ == '__main__':
    main()
