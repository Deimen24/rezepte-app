/*
 * Import from a URL (#/import, #/import?url=...) or from a photo of
 * a book page (text recognition): fetch a preview through the API and
 * show it in the shared recipe form. Saving creates the recipe and,
 * when wanted, loads the page's image as first photo.
 *
 * app.js passes ui = { navigate, categories }.
 */

import * as API from "./api.js";
import {
	h, toast, error_msg, field, back_button, topbar, recipe_form,
} from "./form.js";

const METHOD_LABEL = {
	jsonld: "schema.org",
	heuristic: "Geraten",
	ocr: "Texterkennung",
};
const BOOK_SOURCE = { kind: "book", url: "", book: "", page: null };

function url_from_query(query)
{
	if (!query)
		return "";
	return new URLSearchParams(query).get("url") || "";
}

/*
 * Preview (ImportPreview) -> RecipeInput-like object for the form. A
 * page photo gets a book source with empty title and page.
 */
function preview_to_input(p, url)
{
	const src = p.source || {};
	return {
		category_id: null,
		tags: [],
		favorite: false,
		source: p.method === "ocr" ? Object.assign({}, BOOK_SOURCE)
			: { kind: "url", url: src.url || url, book: "",
			    page: null },
		version: p.version,
	};
}

function hint_label(n)
{
	if (n === 0)
		return "Vorschau";
	return n === 1 ? "1 Hinweis" : n + " Hinweise";
}

function preview_head(p)
{
	const warnings = p.warnings || [];
	return [
		h("p", { class: "preview-head" },
			h("span", { class: "method" },
				METHOD_LABEL[p.method] || p.method),
			h("span", {}, hint_label(warnings.length))),
		warnings.length
			? h("ul", { class: "warnings" },
				warnings.map(w => h("li", {}, w)))
			: null,
	];
}

function image_box(p)
{
	const take = h("input", { type: "checkbox", name: "take_image",
				  checked: true });
	const el = p.image_url
		? h("figure", { class: "preview-img" },
			h("img", { src: p.image_url, alt: "" }),
			h("label", { class: "check" }, take,
				h("span", {}, "Bild übernehmen")))
		: null;
	return { el: el, wanted: () => !!(p.image_url && take.checked) };
}

async function add_image(id, url)
{
	try {
		await API.add_photo_from_url(id, url);
		return true;
	} catch (e) {
		toast("Bild nicht geladen: " + error_msg(e), true);
		return false;
	}
}

function preview_el(p, url, ui)
{
	const img = image_box(p);
	const form = recipe_form(preview_to_input(p, url), ui.categories, {
		cancel_href: "#/",
		on_save: async (input) => {
			const r = await API.create_recipe(input);
			let ok = true;
			if (img.wanted())
				ok = await add_image(r.id, p.image_url);
			if (ok)
				toast("Gespeichert", false);
			ui.navigate("#/recipe/" + r.id);
		},
	});
	return h("div", {}, preview_head(p), img.el, form);
}

/*
 * «Buchseite fotografieren»: the camera (or a saved image) goes to
 * /import/photo and comes back as the same preview.
 */
function photo_form(preview, ui)
{
	const btn = h("button", { type: "button" }, "Foto");
	const file = h("input", { type: "file", accept: "image/*",
				  capture: "environment", class: "hidden",
				  "aria-label": "Buchseite fotografieren",
				  onchange: async (ev) => {
		const f = ev.target.files && ev.target.files[0];
		if (!f)
			return;
		btn.disabled = true;
		btn.replaceChildren(h("span", { class: "spinner" }),
				    "Lesen …");
		preview.replaceChildren();
		try {
			const p = await API.import_photo(f);
			preview.replaceChildren(preview_el(p, "", ui));
		} catch (e) {
			toast(error_msg(e), true);
		} finally {
			btn.disabled = false;
			btn.replaceChildren("Foto");
			ev.target.value = "";
		}
	} });
	btn.addEventListener("click", () => file.click());
	return h("div", { class: "import-photo" },
		h("span", { class: "field-label" }, "Buchseite fotografieren"),
		btn, file);
}

export function view_import(query, ui)
{
	const url = h("input", { name: "url", type: "url", inputmode: "url",
				 placeholder: "https://…", required: true,
				 autocomplete: "off", autofocus: true,
				 value: url_from_query(query) });
	const load = h("button", { type: "submit", class: "btn-primary" },
		       "Laden");
	const preview = h("div", {});
	const fetch_preview = async () => {
		const u = url.value.trim();
		if (u === "")
			return;
		load.disabled = true;
		load.replaceChildren(h("span", { class: "spinner" }),
				     "Laden …");
		preview.replaceChildren();
		try {
			const p = await API.import_fetch(u);
			preview.replaceChildren(preview_el(p, u, ui));
		} catch (e) {
			toast(error_msg(e), true);
		} finally {
			load.disabled = false;
			load.replaceChildren("Laden");
		}
	};
	const form = h("form", { class: "import-form", onsubmit: (ev) => {
		ev.preventDefault();
		fetch_preview();
	} },
		h("div", { class: "row" }, field("Link", url), load));
	if (url.value !== "")
		fetch_preview();
	return h("div", {},
		topbar("Import", back_button("#/")),
		h("main", {}, form, photo_form(preview, ui), preview));
}
