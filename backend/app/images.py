"""Photo processing: EXIF rotation, downscale, re-encode as plain JPEG."""

from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_SIDE = 1600
THUMB_SIDE = 400
JPEG_QUALITY = 85
WHITE = (255, 255, 255)


def _open(data: bytes) -> Image.Image:
	try:
		img = Image.open(BytesIO(data))
		img = ImageOps.exif_transpose(img)
		img.load()
	except (UnidentifiedImageError, OSError,
		Image.DecompressionBombError, ValueError):
		raise ValueError("not an image")
	return img


def _to_rgb(img: Image.Image) -> Image.Image:
	"""Flatten transparency onto white, drop palettes and grayscale."""
	if img.mode in ("RGBA", "LA") or (
			img.mode == "P" and "transparency" in img.info):
		rgba = img.convert("RGBA")
		base = Image.new("RGB", rgba.size, WHITE)
		base.paste(rgba, mask=rgba.getchannel("A"))
		return base
	if img.mode != "RGB":
		return img.convert("RGB")
	return img


def _fit(img: Image.Image, side: int) -> Image.Image:
	"""Shrink so the longest side is at most `side`; never upscale."""
	if max(img.size) <= side:
		return img
	out = img.copy()
	out.thumbnail((side, side), Image.Resampling.LANCZOS)
	return out


def _jpeg(img: Image.Image) -> bytes:
	buf = BytesIO()
	img.save(buf, "JPEG", quality=JPEG_QUALITY, optimize=True)
	return buf.getvalue()


def process(data: bytes) -> tuple[bytes, bytes]:
	"""Return (full, thumb) JPEG bytes without metadata.

	Raises ValueError("not an image") for anything Pillow rejects.
	"""
	img = _to_rgb(_open(data))
	full = _fit(img, MAX_SIDE)
	thumb = _fit(full, THUMB_SIDE)
	return _jpeg(full), _jpeg(thumb)
