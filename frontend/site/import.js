/*
 * Import from a URL (#/import, #/import?url=...): fetch a preview
 * through the API and show it in the shared recipe form. Saving
 * creates the recipe and, when wanted, loads the page's image as
 * first photo.
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
};

function url_from_query(query)
{
	if (!query)
		return "";
	return new URLSearchParams(query).get("url") || "";
}

/* Preview (ImportPreview) -> RecipeInput-like object for the form. */
function preview_to_input(p, url)
{
	const src = p.source || {};
	return {
		category_id: null,
		tags: [],
		favorite: false,
		source: { kind: "url", url: src.url || url, book: "",
			  page: null },
		version: p.version,
	};
}

function preview_head(p)
{
	const warnings = p.warnings || [];
	return [
		h("p", { class: "preview-head" },
			h("span", { class: "method" },
				METHOD_LABEL[p.method] || p.method),
			h("span", {}, warnings.length
				? warnings.length + " Hinweise" : "Vorschau")),
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
		h("main", {}, form, preview));
}
