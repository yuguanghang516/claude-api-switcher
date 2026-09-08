"""Build the code-native switch mark as SVG, PNG and multi-resolution ICO."""
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'assets'
BLUE = '#2563EB'
WHITE = '#FFFFFF'
ICE = '#B8D5FF'
# Two opposed solid arrows: deliberately legible without fine internal details.
TOP = [(60, 72), (150, 72), (150, 49), (198, 94), (150, 139), (150, 115), (60, 115)]
BOTTOM = [(196, 141), (106, 141), (106, 117), (58, 162), (106, 207), (106, 184), (196, 184)]

def build():
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">',
           f'<rect x="8" y="8" width="240" height="240" rx="56" fill="{BLUE}"/>']
    im = Image.new('RGBA', (1024, 1024))
    draw = ImageDraw.Draw(im)
    draw.rounded_rectangle((32, 32, 992, 992), radius=224, fill=BLUE)
    for points, color in ((TOP, WHITE), (BOTTOM, ICE)):
        svg.append(f'<polygon points="{" ".join(f"{x},{y}" for x,y in points)}" fill="{color}"/>')
        draw.polygon([(x*4, y*4) for x,y in points], fill=color)
    svg.append('</svg>')
    (ASSETS / 'app_icon.svg').write_text('\n'.join(svg), encoding='utf-8')
    im.resize((512, 512), Image.Resampling.LANCZOS).save(ASSETS / 'app_icon.png')
    im.save(ASSETS / 'app_icon.ico', sizes=[(n,n) for n in (16,24,32,48,64,128,256)])

if __name__ == '__main__':
    build()
