"""Render the vector-native Interlink mark into Windows icon sizes."""
from pathlib import Path
from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parents[1] / 'assets'
NAVY, WHITE, AQUA = '#12263A', '#F4F8FC', '#65D6CD'
COMMANDS = [
    ('M', (184, 60)), ('L', (117, 60)),
    ('C', (81, 60), (54, 87), (54, 122)), ('L', (54, 156)),
    ('L', (86, 124)), ('L', (86, 122)),
    ('C', (86, 104), (99, 91), (117, 91)),
    ('L', (153, 91)), ('L', (184, 60)),
]

def ribbon():
    points = []
    for command in COMMANDS:
        kind, *coords = command
        if kind in ('M', 'L'):
            points.append(coords[0])
        else:
            p0, p1, p2, p3 = points[-1], *coords
            for step in range(1, 65):
                t = step / 64
                points.append(tuple((1-t)**3*p0[i] + 3*(1-t)**2*t*p1[i]
                                    + 3*(1-t)*t*t*p2[i] + t**3*p3[i] for i in (0, 1)))
    return points

def build():
    path = ' '.join(c[0] + ' '.join(f'{x},{y}' for x,y in c[1:]) for c in COMMANDS) + ' Z'
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">
<rect x="8" y="8" width="240" height="240" rx="58" fill="{NAVY}"/>
<path d="{path}" fill="{WHITE}"/>
<path d="{path}" transform="rotate(180 128 128)" fill="{AQUA}"/>
</svg>'''
    (ASSETS / 'app_icon.svg').write_text(svg, encoding='utf-8')
    im = Image.new('RGBA', (1024, 1024))
    draw = ImageDraw.Draw(im)
    draw.rounded_rectangle((32, 32, 992, 992), radius=232, fill=NAVY)
    points = ribbon()
    draw.polygon([(x*4,y*4) for x,y in points], fill=WHITE)
    draw.polygon([((256-x)*4,(256-y)*4) for x,y in points], fill=AQUA)
    im.resize((512,512), Image.Resampling.LANCZOS).save(ASSETS / 'app_icon.png')
    im.save(ASSETS / 'app_icon.ico', sizes=[(n,n) for n in (16,24,32,48,64,128,256)])

if __name__ == '__main__':
    build()
