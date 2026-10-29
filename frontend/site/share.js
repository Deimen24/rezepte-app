/*
 * Public recipe page (#/s/TOKEN): title, category, tags, photos and
 * the own version with the portion stepper. No login, no edit
 * controls. An unknown token shows «Nicht gefunden».
 *
 * app.js passes ui = { version_section } so the ingredient and step
 * rendering stays in one place.
 */

import * as API from "./api.js";
import { h, topbar, error_msg } from "./form.js";

const FOOTER = "Rezepte";
/* Servings state key; keeps shared pages apart from own recipes. */
const STORE_ID_PREFIX = "s:";

function join_present(parts, sep)
{
	return parts.filter(p => p !== "" && p !== null &&
			     p !== undefined).join(sep);
}

function photo_strip(urls)
{
	if (!urls || urls.length === 0)
		return null;
	return h("div", { class: "photos photos-full" },
		urls.map(u => h("figure", { class: "photo" },
				h("img", { src: u, alt: "",
					   loading: "lazy" }))));
}

/* The server answers an unknown token with 404 "not found". */
function error_text(e)
{
	return /not found/i.test(error_msg(e)) ? "Nicht gefunden"
					       : error_msg(e);
}

function error_page(e)
{
	return h("div", { class: "shared" },
		topbar(FOOTER),
		h("main", {},
			h("p", { class: "empty" }, error_text(e))));
}

function shared_el(token, r, ui)
{
	const tags = (r.tags || []).map(t => "#" + t).join(" ");
	const meta = join_present([r.category, tags], " · ");
	return h("div", { class: "shared" },
		topbar(r.title),
		h("main", {},
			h("h1", {}, r.title),
			meta ? h("p", { class: "meta-line" }, meta) : null,
			photo_strip(r.photos),
			ui.version_section(STORE_ID_PREFIX + token, r.own),
			h("footer", { class: "foot" }, FOOTER)));
}

export async function view_shared(token, ui)
{
	let r;
	try {
		r = await API.get_shared(token);
	} catch (e) {
		return error_page(e);
	}
	return shared_el(token, r, ui);
}
