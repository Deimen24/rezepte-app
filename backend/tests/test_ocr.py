"""OCR import: text splitting, image preparation, the tesseract call and
POST /api/import/photo with the OCR mocked."""

import subprocess
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from app.importer import ocr
from app.importer.ocr import (
	OcrError,
	clean_lines,
	prepare_image,
	run_tesseract,
	split_text,
)
from app.services.photos import MAX_UPLOAD

FIXTURE = Path(__file__).parent / "fixtures" / "ocr_page.txt"
PAGE = FIXTURE.read_text(encoding="utf-8")
PREVIEW_KEYS = {"source", "version", "image_url", "method", "warnings"}

BARE = """Pfannkuchen

200 g Mehl
2 Eier
300 ml Milch

Alles verrühren und in der Pfanne backen.

Mit Zucker bestreuen.
"""


def jpeg(size=(640, 480), mode="RGB") -> bytes:
	buf = BytesIO()
	Image.new(mode, size, (200, 50, 50) if mode == "RGB" else 128
		  ).save(buf, "JPEG")
	return buf.getvalue()


def upload(client, data=None, name="seite.jpg", mime="image/jpeg"):
	return client.post("/api/import/photo",
			   files={"file": (name, data or jpeg(), mime)})


def test_split_fixture_page():
	data = split_text(PAGE)
	assert data.title == "Kürbissuppe mit Ingwer"
	assert data.servings == 4
	assert data.prep_minutes == 30
	assert data.cook_minutes is None
	assert data.intro == ""
	assert data.ingredient_lines == [
		"800 g Hokkaido-Kürbis", "1 Zwiebel", "2 EL Olivenöl",
		"1 Stück Ingwer (ca. 2 cm)", "800 ml Gemüsebrühe",
		"½ TL Salz"]
	assert len(data.steps) == 3
	assert data.steps[2] == ("Mit Brühe ablöschen und 20 Minuten "
				 "köcheln lassen. Fein pürieren und mit "
				 "Salz abschmecken.")
	assert data.warnings == []


def test_hyphenation_joined_across_lines():
	data = split_text(PAGE)
	assert "Zwiebeln und Ingwer schälen" in data.steps[0]
	assert "Zwie-" not in data.steps[0]


def test_compound_hyphen_before_capital_is_kept():
	assert clean_lines("Süsskartoffel-\nPüree") == ["Süsskartoffel-",
							"Püree"]


def test_without_keywords_amount_lines_are_ingredients():
	data = split_text(BARE)
	assert data.title == "Pfannkuchen"
	assert data.ingredient_lines == ["200 g Mehl", "2 Eier",
					 "300 ml Milch"]
	assert data.steps == ["Alles verrühren und in der Pfanne backen.",
			      "Mit Zucker bestreuen."]
	assert data.warnings == ["Zutaten geraten", "Schritte geraten"]


def test_ingredients_keyword_only_cuts_at_step_like_line():
	text = ("Kuchen\nZutaten\n1 Ei\n2 EL Zucker\n"
		"Alles verrühren und bei 180 Grad 30 Minuten im Ofen "
		"backen, bis es gut ist.\nAbkühlen lassen.")
	data = split_text(text)
	assert data.ingredient_lines == ["1 Ei", "2 EL Zucker"]
	assert len(data.steps) == 1
	assert data.steps[0].startswith("Alles verrühren")
	assert data.steps[0].endswith("Abkühlen lassen.")
	assert data.warnings == ["Schritte geraten"]


def test_steps_merged_across_lines():
	text = "Suppe\nZubereitung\nZwiebeln\nhacken und\nanbraten."
	assert split_text(text).steps == ["Zwiebeln hacken und anbraten."]


@pytest.mark.parametrize("marker", ["1.", "1)", "Schritt 1:", "Schritt"])
def test_numbered_steps_split(marker):
	text = (f"Suppe\nZubereitung\n{marker} Zwiebeln hacken.\n"
		f"{marker.replace('1', '2')} Anbraten.")
	assert split_text(text).steps == ["Zwiebeln hacken.", "Anbraten."]


def test_blank_line_splits_steps():
	text = "Suppe\nZubereitung\nZwiebeln hacken.\n\nAnbraten."
	assert split_text(text).steps == ["Zwiebeln hacken.", "Anbraten."]


def test_time_line_is_not_a_keyword_line():
	text = ("Suppe\nZubereitung: 20 Min\nZutaten\n1 Ei\n"
		"Zubereitung\nRühren.")
	data = split_text(text)
	assert data.prep_minutes == 20
	assert data.ingredient_lines == ["1 Ei"]
	assert data.steps == ["Rühren."]


def test_missing_title_is_warned():
	data = split_text("Zutaten\n1 Ei")
	assert data.title == ""
	assert "Titel nicht gefunden" in data.warnings


def test_multiple_spaces_collapsed():
	data = split_text("Suppe\nZutaten\n200   g   Mehl")
	assert data.ingredient_lines == ["200 g Mehl"]


def test_prepare_image_returns_capped_grayscale_png():
	out = prepare_image(jpeg((5000, 2000)))
	img = Image.open(BytesIO(out))
	assert img.format == "PNG"
	assert img.mode == "L"
	assert img.size == (2500, 1000)


def test_prepare_image_does_not_upscale():
	img = Image.open(BytesIO(prepare_image(jpeg((640, 480)))))
	assert img.size == (640, 480)


def test_prepare_image_rejects_non_image():
	with pytest.raises(ValueError):
		prepare_image(b"hello")


def test_run_tesseract_passes_image_and_returns_text(monkeypatch):
	seen = {}

	def fake_run(cmd, **kwargs):
		seen["cmd"] = cmd
		seen["kwargs"] = kwargs
		return subprocess.CompletedProcess(cmd, 0, b"Text\n", b"")

	monkeypatch.setattr(subprocess, "run", fake_run)
	assert run_tesseract(b"png") == "Text\n"
	assert seen["cmd"][:3] == ["tesseract", "stdin", "stdout"]
	assert "-l" in seen["cmd"] and "deu+eng" in seen["cmd"]
	assert seen["kwargs"]["input"] == b"png"
	assert seen["kwargs"]["timeout"] == ocr.TIMEOUT


def raising(exc):
	def fake_run(cmd, **kwargs):
		raise exc
	return fake_run


def test_run_tesseract_not_installed(monkeypatch):
	monkeypatch.setattr(subprocess, "run", raising(FileNotFoundError()))
	with pytest.raises(OcrError) as info:
		run_tesseract(b"png")
	assert info.value.detail == "Texterkennung nicht installiert"


def test_run_tesseract_timeout(monkeypatch):
	monkeypatch.setattr(subprocess, "run",
			    raising(subprocess.TimeoutExpired("t", 1)))
	with pytest.raises(OcrError) as info:
		run_tesseract(b"png")
	assert info.value.detail == "Zeitüberschreitung"


def test_run_tesseract_non_zero_exit(monkeypatch):
	monkeypatch.setattr(subprocess, "run", lambda cmd, **kw:
			    subprocess.CompletedProcess(cmd, 1, b"", b"err"))
	with pytest.raises(OcrError) as info:
		run_tesseract(b"png")
	assert info.value.detail == "Texterkennung fehlgeschlagen"


@pytest.fixture
def ocr_text(monkeypatch):
	"""Replace the tesseract call; returns a dict to set the text."""
	state = {"text": PAGE, "images": []}

	def fake(image: bytes) -> str:
		state["images"].append(image)
		return state["text"]

	monkeypatch.setattr(ocr, "run_tesseract", fake)
	return state


def test_photo_preview(auth_client, ocr_text):
	resp = upload(auth_client)
	assert resp.status_code == 200, resp.text
	body = resp.json()
	assert set(body) == PREVIEW_KEYS
	assert body["method"] == "ocr"
	assert body["image_url"] is None
	assert body["source"] == {"kind": "none", "url": None,
				  "book": None, "page": None}
	assert body["warnings"][0] == "Text prüfen"
	version = body["version"]
	assert version["title"] == "Kürbissuppe mit Ingwer"
	assert version["servings"] == 4
	assert version["prep_minutes"] == 30
	assert len(version["ingredients"]) == 6
	first = version["ingredients"][0]
	assert first["amount"] == "800"
	assert first["unit"] == "g"
	assert first["name"] == "Hokkaido-Kürbis"
	assert first["raw"] == "800 g Hokkaido-Kürbis"
	assert version["ingredients"][5]["amount"] == "0.5"
	assert len(version["steps"]) == 3
	# the OCR engine gets the prepared PNG, not the upload
	assert ocr_text["images"][0].startswith(b"\x89PNG")


def test_photo_preview_guessed_warnings(auth_client, ocr_text):
	ocr_text["text"] = BARE
	body = upload(auth_client).json()
	assert body["warnings"] == ["Text prüfen", "Zutaten geraten",
				    "Schritte geraten"]


def test_photo_preview_empty_text_is_422(auth_client, ocr_text):
	ocr_text["text"] = " \n\n"
	resp = upload(auth_client)
	assert resp.status_code == 422
	assert resp.json() == {"detail": "Kein Text erkannt"}


def test_photo_preview_ocr_error_is_422(auth_client, monkeypatch):
	def fail(image):
		raise OcrError("Texterkennung nicht installiert")
	monkeypatch.setattr(ocr, "run_tesseract", fail)
	resp = upload(auth_client)
	assert resp.status_code == 422
	assert resp.json() == {"detail": "Texterkennung nicht installiert"}


def test_photo_preview_not_an_image_is_415(auth_client, ocr_text):
	resp = upload(auth_client, data=b"hello world", name="a.txt",
		      mime="text/plain")
	assert resp.status_code == 415
	assert resp.json() == {"detail": "not an image"}
	assert ocr_text["images"] == []


def test_photo_preview_too_large_is_413(auth_client, ocr_text):
	resp = upload(auth_client, data=jpeg() + b"\0" * MAX_UPLOAD)
	assert resp.status_code == 413
	assert ocr_text["images"] == []


def test_photo_preview_requires_login(client):
	assert upload(client).status_code == 401
