"""Resolve one circular avatar image per entity — fetched once and
cached (not once per frame), with a generated colored-initials circle as
the fallback when there's no image URL, the fetch fails, or the file
can't be decoded as an image."""
import hashlib
import io

import requests
from PIL import Image, ImageDraw, ImageFont

AVATAR_PALETTE = [
    "#7C3AED", "#2563EB", "#059669", "#D97706", "#DC2626",
    "#DB2777", "#0891B2", "#65A30D", "#9333EA", "#EA580C",
]


def _color_for(key: str) -> str:
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return AVATAR_PALETTE[int(digest, 16) % len(AVATAR_PALETTE)]


def _make_circular(img: Image.Image, size: int) -> Image.Image:
    img = img.convert("RGBA")
    # cover-fit: scale so the shorter side fills `size`, crop the rest
    scale = size / min(img.size)
    resized = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))))
    left = (resized.width - size) // 2
    top = (resized.height - size) // 2
    cropped = resized.crop((left, top, left + size, top + size))

    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(cropped, (0, 0), mask)
    return out


def initials_avatar(entity_name: str, size: int) -> Image.Image:
    initials = "".join(w[0].upper() for w in entity_name.split()[:2]) or "?"
    color = _color_for(entity_name)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((0, 0, size, size), fill=color)
    try:
        font = ImageFont.truetype("arial.ttf", int(size * 0.4))
    except OSError:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), initials, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1]), initials, font=font, fill="white")
    return img


class ImageResolver:
    """One instance per render job — caches fetched images by URL so a
    100-frame race with the same 10 entities does 10 fetches, not 1000."""

    def __init__(self, size: int = 64, timeout: float = 5.0):
        self.size = size
        self.timeout = timeout
        self._cache: dict[str, Image.Image] = {}
        # requests.get() builds a brand-new SSL context (and reloads the CA
        # bundle from disk — ~0.7s each, profiled) on every single call. A
        # session reuses one connection pool/SSL context across every fetch
        # this resolver makes, which is the entire point of caching by URL
        # in the first place.
        self._session = requests.Session()

    def resolve(self, entity_name: str, image_url: str | None) -> Image.Image:
        cache_key = image_url or f"__initials__:{entity_name}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        avatar = self._fetch_and_crop(image_url) if image_url else None
        if avatar is None:
            avatar = initials_avatar(entity_name, self.size)

        self._cache[cache_key] = avatar
        return avatar

    def _fetch_and_crop(self, url: str) -> Image.Image | None:
        try:
            resp = self._session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            img = Image.open(io.BytesIO(resp.content))
            return _make_circular(img, self.size)
        except Exception:
            return None
