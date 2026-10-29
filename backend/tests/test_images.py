"""Image processing: size limits, rotation, colour modes, metadata."""

from io import BytesIO

import pytest
from PIL import Image

from app import images

ORIENTATION_TAG = 0x0112
ROTATE_90_CW = 6


def make(size, mode="RGB", fmt="JPEG", exif=None, color=(200, 30, 30)):
	img = Image.new(mode, size, color)
	buf = BytesIO()
	kwargs = {}
	if exif is not None:
		kwargs["exif"] = exif
	img.save(buf, fmt, **kwargs)
	return buf.getvalue()


def load(data: bytes) -> Image.Image:
	return Image.open(BytesIO(data))


def test_large_jpeg_is_scaled_to_max_and_thumb_side():
	full, thumb = images.process(make((3000, 2000)))
	assert load(full).size == (1600, 1067)
	assert load(thumb).size == (400, 267)


def test_portrait_uses_height_as_longest_side():
	full, thumb = images.process(make((2000, 3000)))
	assert load(full).size == (1067, 1600)
	assert load(thumb).size == (267, 400)


def test_small_image_is_not_upscaled():
	full, thumb = images.process(make((800, 600)))
	assert load(full).size == (800, 600)
	assert load(thumb).size == (400, 300)


def test_tiny_image_keeps_size_in_both_outputs():
	full, thumb = images.process(make((300, 200)))
	assert load(full).size == (300, 200)
	assert load(thumb).size == (300, 200)


def test_outputs_are_jpeg_rgb():
	full, thumb = images.process(make((800, 600)))
	for data in (full, thumb):
		img = load(data)
		assert img.format == "JPEG"
		assert img.mode == "RGB"


def test_png_with_alpha_is_flattened_onto_white():
	data = make((100, 100), mode="RGBA", fmt="PNG",
		    color=(0, 0, 0, 0))
	full, _ = images.process(data)
	img = load(full)
	assert img.mode == "RGB"
	r, g, b = img.getpixel((50, 50))
	assert min(r, g, b) > 245


def test_exif_orientation_is_applied():
	exif = Image.Exif()
	exif[ORIENTATION_TAG] = ROTATE_90_CW
	full, thumb = images.process(make((800, 400), exif=exif))
	assert load(full).size == (400, 800)
	assert load(thumb).size == (200, 400)


def test_output_has_no_exif():
	exif = Image.Exif()
	exif[ORIENTATION_TAG] = ROTATE_90_CW
	exif[0x010F] = "ACME Camera"
	full, thumb = images.process(make((800, 400), exif=exif))
	for data in (full, thumb):
		img = load(data)
		assert dict(img.getexif()) == {}
		assert "exif" not in img.info


def test_grayscale_input_works():
	full, thumb = images.process(make((1000, 500), mode="L", color=90))
	assert load(full).size == (1000, 500)
	assert load(full).mode == "RGB"
	assert load(thumb).size == (400, 200)


def test_palette_png_works():
	data = make((500, 500), mode="P", fmt="PNG", color=3)
	full, _ = images.process(data)
	assert load(full).mode == "RGB"


@pytest.mark.parametrize("data", [b"", b"not an image at all",
				  b"\xff\xd8\xff\xe0garbage",
				  b"<html><body>hi</body></html>"])
def test_garbage_raises_value_error(data):
	with pytest.raises(ValueError, match="not an image"):
		images.process(data)


def test_truncated_jpeg_raises_value_error():
	data = make((800, 600))
	with pytest.raises(ValueError, match="not an image"):
		images.process(data[: len(data) // 2])


def test_decompression_bomb_raises_value_error(monkeypatch):
	monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1000)
	with pytest.raises(ValueError, match="not an image"):
		images.process(make((100, 100)))
