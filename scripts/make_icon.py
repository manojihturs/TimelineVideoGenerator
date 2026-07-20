"""Generates static/reelframe.ico — the brand mark (amber ring on ink bg)."""
import os
from PIL import Image, ImageDraw

SIZES = [16, 24, 32, 48, 64, 128, 256]
INK = (20, 23, 28, 255)
AMBER = (232, 163, 61, 255)
AMBER_DIM = (107, 85, 39, 255)

def make(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = max(1, size // 16)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=size // 5, fill=INK)
    cx = cy = size / 2
    outer_r = size / 2 - pad * 1.6
    inner_r = outer_r * 0.42
    d.ellipse([cx - outer_r, cy - outer_r, cx + outer_r, cy + outer_r], outline=AMBER, width=max(1, size // 10))
    d.ellipse([cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r], fill=AMBER)
    return img

frames = [make(s) for s in SIZES]
out_dir = os.path.join(os.path.dirname(__file__), "..", "static")
os.makedirs(out_dir, exist_ok=True)
out_path = os.path.join(out_dir, "reelframe.ico")
frames[-1].save(out_path, format="ICO", sizes=[(s, s) for s in SIZES])
print("wrote", out_path)
