import sys
from PIL import Image

def remove_bg(img_path):
    img = Image.open(img_path).convert("RGBA")
    pixels = img.load()
    
    # Sample top-left corner for background color
    bg_r, bg_g, bg_b = pixels[0, 0][:3]
    
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = pixels[x, y]
            dist = ((r - bg_r)**2 + (g - bg_g)**2 + (b - bg_b)**2)**0.5
            if dist < 18:
                pixels[x, y] = (r, g, b, 0)
            elif dist < 60:
                alpha = int((dist - 18) / 42 * 255)
                # optionally blend color to black to avoid fringing
                pixels[x, y] = (r, g, b, alpha)
            else:
                pixels[x, y] = (r, g, b, 255)
                
    # Crop to bounding box of non-transparent pixels
    bbox = img.getbbox()
    if bbox:
        # Add some padding
        pad = 20
        bbox = (max(0, bbox[0]-pad), max(0, bbox[1]-pad), min(img.width, bbox[2]+pad), min(img.height, bbox[3]+pad))
        img = img.crop(bbox)
        
    img.save(img_path, "PNG")

if __name__ == "__main__":
    remove_bg("c:/Coding/TAPIOD/gateway-dashboard/public/logo.png")
