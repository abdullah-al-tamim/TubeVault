from pathlib import Path
from PIL import Image, ImageDraw
root = Path(__file__).resolve().parent.parent
(root/'assets').mkdir(exist_ok=True)
image = Image.new('RGBA', (256,256), (0,0,0,0))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((8,8,248,248), radius=52, fill='#6ee7b7')
draw.rounded_rectangle((62,75,194,198), radius=14, outline='#123c2e', width=12)
draw.rounded_rectangle((47,55,209,94), radius=9, fill='#6ee7b7', outline='#123c2e', width=12)
draw.rounded_rectangle((102,117,154,130), radius=5, fill='#123c2e')
image.save(root/'assets'/'tubevault.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
