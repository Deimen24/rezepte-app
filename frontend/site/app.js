/*
 * Recipe app: hash router and views. No framework, no build step.
 *
 * Routes: #/login, #/ (list), #/recipe/ID, #/new, #/edit/ID,
 * #/cook/ID (cook.js), #/import (import.js). All user text is
 * rendered through h() / textContent, never innerHTML. DOM helpers
 * and the recipe form live in form.js.
 */

import * as API from "./api.js";
import { view_cook } from "./cook.js";
import { view_import } from "./import.js";
import {
	h, toast, error_msg, field, back_button, topbar, str, fmt_amount,
	split_csv, empty_input, recipe_to_input, recipe_form,
} from "./form.js";

const DEBOUNCE_MS = 300;
const LOADING_DELAY_MS = 150;
const RATING_MAX = 5;
/* Hash suffix set by cooking mode: open the cook-log form. */
const COOKED_FLAG = "?cooked";

const state = {
	user: null,
	categories: [],
	tags: [],
};

/* List filters survive navigation to a recipe and back. */
const filter = {
	q: "",
	category: "",
	tags: [],
	ingredients: "",
	favorite: false,
};

const ROUTES = [
	[/^#\/login$/, view_login],
	[/^#\/?$/, view_list],
	[/^#\/recipe\/(\d+)(\?cooked)?$/, view_detail],
	[/^#\/new$/, view_form],
	[/^#\/edit\/(\d+)$/, view_form],
	[/^#\/import(?:\?(.*))?$/, view_import_route],
	[/^#\/cook\/(\d+)$/, (id) => view_cook(id, {
		h: h, navigate: navigate, ingredient_text: ingredient_text })],
];

let render_seq = 0;

/* ------------------------------------------------------------------ */
/* DOM helpers                                                         */
/* ------------------------------------------------------------------ */

function show(el, keep_scroll)
{
	const app = document.getElementById("app");
	app.replaceChildren(el);
	if (!keep_scroll)
		window.scrollTo(0, 0);
}

function debounce(fn, ms)
{
	let timer = null;
	return (...args) => {
		clearTimeout(timer);
		timer = setTimeout(() => fn(...args), ms);
	};
}

/*
 * Overflow menu (native <details>), closed on any tap outside.
 */
function menu(...items)
{
	const d = h("details", { class: "menu" },
		h("summary", { class: "btn btn-icon", "aria-label": "Menü" },
			"⋯"),
		h("div", { class: "menu-list" }, items));
	const close = (ev) => {
		if (!d.contains(ev.target))
			d.removeAttribute("open");
	};
	d.addEventListener("toggle", () => {
		if (d.open)
			document.addEventListener("click", close);
		else
			document.removeEventListener("click", close);
	});
	return d;
}

/* ------------------------------------------------------------------ */
/* Formatting                                                          */
/* ------------------------------------------------------------------ */

function fmt_minutes(n)
{
	return n === null || n === undefined ? "" : n + " Min.";
}

/* "2026-10-29" or an ISO datetime -> "29.10.2026" */
function fmt_date(s)
{
	const m = String(s || "").match(/^(\d{4})-(\d{2})-(\d{2})/);
	return m ? m[3] + "." + m[2] + "." + m[1] : str(s);
}

function pad2(n)
{
	return String(n).padStart(2, "0");
}

/* Local date as yyyy-mm-dd (not UTC). */
function today_iso()
{
	const d = new Date();
	return d.getFullYear() + "-" + pad2(d.getMonth() + 1) + "-" +
	       pad2(d.getDate());
}

function stars_text(n)
{
	if (!n)
		return "";
	return "★".repeat(n) + "☆".repeat(RATING_MAX - n);
}

function pressed(on)
{
	return on ? "true" : "false";
}

function join_present(parts, sep)
{
	return parts.filter(p => p !== "" && p !== null &&
			     p !== undefined).join(sep);
}

/* ------------------------------------------------------------------ */
/* Router                                                              */
/* ------------------------------------------------------------------ */

function navigate(hash)
{
	if (location.hash === hash)
		render();
	else
		location.hash = hash;
}

function find_route(hash)
{
	for (const [re, view] of ROUTES) {
		const m = hash.match(re);
		if (m)
			return { view: view, arg: m[1] };
	}
	return null;
}

async function render()
{
	const seq = ++render_seq;
	const hash = location.hash || "#/";
	const r = find_route(hash);
	if (!r)
		return navigate("#/");
	if (!state.user && r.view !== view_login)
		return navigate("#/login");
	if (state.user && r.view === view_login)
		return navigate("#/");
	const timer = setTimeout(() => {
		if (seq === render_seq)
			show(h("p", { class: "loading" }, "Laden …"));
	}, LOADING_DELAY_MS);
	try {
		const el = await r.view(r.arg);
		if (seq === render_seq)
			show(el);
	} catch (e) {
		if (seq === render_seq)
			show(view_error(e));
	} finally {
		clearTimeout(timer);
	}
}

function view_error(e)
{
	return h("div", {},
		topbar("Fehler", back_button("#/")),
		h("main", {},
			h("p", { class: "empty" }, error_msg(e)),
			h("div", { class: "actions" },
				h("a", { class: "btn", href: "#/" },
					"Zur Liste"))));
}

/* ------------------------------------------------------------------ */
/* Login                                                               */
/* ------------------------------------------------------------------ */

function view_login()
{
	const user = h("input", { name: "username", autocomplete: "username",
				  autocapitalize: "none", required: true,
				  autofocus: true });
	const pass = h("input", { name: "password", type: "password",
				  autocomplete: "current-password",
				  required: true });
	const btn = h("button", { type: "submit", class: "btn-primary" },
		      "Anmelden");
	const form = h("form", { class: "login", onsubmit: async (ev) => {
		ev.preventDefault();
		btn.disabled = true;
		try {
			await API.login(user.value.trim(), pass.value);
			state.user = await API.me();
			navigate("#/");
		} catch (e) {
			toast(error_msg(e), true);
			btn.disabled = false;
		}
	} },
		h("h1", {}, "Rezepte"),
		field("Benutzername", user),
		field("Passwort", pass),
		h("div", { class: "actions" }, btn));
	return h("main", {}, form);
}

async function logout()
{
	try {
		await API.logout();
	} catch (e) {
		/* Session may already be gone; log out locally anyway. */
	}
	state.user = null;
	navigate("#/login");
}

/* ------------------------------------------------------------------ */
/* Taxonomy                                                            */
/* ------------------------------------------------------------------ */

async function load_taxonomy()
{
	const [cats, tags] = await Promise.all([
		API.list_categories(), API.list_tags()]);
	state.categories = cats || [];
	state.tags = tags || [];
}

function category_options(selected, empty_label)
{
	const opts = [h("option", { value: "" }, empty_label)];
	const sel = String(selected);
	for (const c of state.categories)
		opts.push(h("option", { value: c.id,
					selected: String(c.id) === sel },
				c.name));
	return opts;
}

/* ------------------------------------------------------------------ */
/* List                                                                */
/* ------------------------------------------------------------------ */

function filter_params()
{
	return {
		q: filter.q.trim(),
		category: filter.category,
		tags: filter.tags.join(","),
		ingredients: split_csv(filter.ingredients).join(","),
		favorite: filter.favorite ? "true" : "",
	};
}

function star()
{
	return h("span", { class: "star", "aria-label": "Favorit" }, "★");
}

function cooked_line(r)
{
	if (!r.cooked_count)
		return null;
	const last = r.last_cooked ? "zuletzt " + fmt_date(r.last_cooked) : "";
	return h("div", { class: "meta" },
		join_present([r.cooked_count + "× gekocht", last], ", "));
}

function recipe_card(r)
{
	const cat = r.category ? r.category.name : "";
	const tags = (r.tags || []).map(t => "#" + t).join(" ");
	const meta = join_present([cat, tags], " · ");
	return h("li", {},
		h("a", { class: "card", href: "#/recipe/" + r.id },
			r.thumb_url ? h("img", { class: "thumb", alt: "",
						 src: r.thumb_url,
						 loading: "lazy" }) : null,
			h("div", { class: "body" },
				h("div", { class: "title" },
					r.favorite ? star() : null,
					h("span", {}, r.title)),
				meta ? h("div", { class: "meta" }, meta) : null,
				cooked_line(r))));
}

async function fill_list(ul)
{
	let items;
	try {
		items = await API.list_recipes(filter_params());
	} catch (e) {
		toast(error_msg(e), true);
		return;
	}
	ul.replaceChildren(...items.map(recipe_card));
	if (items.length === 0)
		ul.append(h("li", { class: "empty" },
			     "Keine Rezepte gefunden"));
}

function tag_chip(name, on_change)
{
	const active = filter.tags.includes(name);
	return h("button", { type: "button", class: "chip",
			     "aria-pressed": pressed(active),
			     onclick: (ev) => {
		const on = ev.currentTarget.getAttribute("aria-pressed") !==
			   "true";
		ev.currentTarget.setAttribute("aria-pressed", pressed(on));
		if (on)
			filter.tags.push(name);
		else
			filter.tags = filter.tags.filter(t => t !== name);
		on_change();
	} }, name);
}

function filter_bar(on_change)
{
	const slow = debounce(on_change, DEBOUNCE_MS);
	const q = h("input", { type: "search", placeholder: "Suchen …",
			       "aria-label": "Suche", value: filter.q,
			       oninput: (ev) => {
		filter.q = ev.target.value;
		slow();
	} });
	const cat = h("select", { "aria-label": "Kategorie", onchange: (ev) => {
		filter.category = ev.target.value;
		on_change();
	} }, category_options(filter.category, "Alle Kategorien"));
	const ing = h("input", { placeholder: "Zutaten: Kürbis, Feta",
				 "aria-label": "Zutaten",
				 value: filter.ingredients,
				 oninput: (ev) => {
		filter.ingredients = ev.target.value;
		slow();
	} });
	const fav = h("button", { type: "button", class: "chip",
				  "aria-pressed": pressed(filter.favorite),
				  onclick: (ev) => {
		filter.favorite = !filter.favorite;
		ev.currentTarget.setAttribute("aria-pressed",
					      pressed(filter.favorite));
		on_change();
	} }, "★ Favoriten");
	/* Drop selected tags that no longer exist. */
	const names = state.tags.map(t => t.name);
	filter.tags = filter.tags.filter(t => names.includes(t));
	return h("div", { class: "filters" },
		q, cat, ing,
		h("div", { class: "chips" }, fav,
			names.map(n => tag_chip(n, on_change))));
}

async function view_list()
{
	await load_taxonomy();
	const ul = h("ul", { class: "cards" });
	const reload = () => fill_list(ul);
	await fill_list(ul);
	return h("div", {},
		topbar("Rezepte",
			h("a", { class: "btn btn-primary", href: "#/new" },
				"+ Neu"),
			h("a", { class: "btn", href: "#/import" }, "Import"),
			menu(h("a", { href: API.export_url(),
				      download: "rezepte.zip" }, "Export"),
			     h("button", { type: "button", onclick: logout },
			       "Abmelden"))),
		h("main", {}, filter_bar(reload), ul));
}

/* ------------------------------------------------------------------ */
/* Detail                                                              */
/* ------------------------------------------------------------------ */

function source_line(src)
{
	if (!src || src.kind === "none")
		return null;
	if (src.kind === "url" && src.url) {
		let text = src.url;
		try {
			text = new URL(src.url).hostname;
		} catch (e) {
			/* keep raw text */
		}
		return h("p", { class: "meta-line" }, "Quelle: ",
			h("a", { href: src.url, target: "_blank",
				 rel: "noopener noreferrer" }, text));
	}
	if (src.kind === "book") {
		const page = src.page ? "Seite " + src.page : "";
		return h("p", { class: "meta-line" }, "Quelle: ",
			join_present([src.book, page], ", "));
	}
	return null;
}

/* "250 g Mehl (gesiebt)" for cooking mode. */
function ingredient_text(i)
{
	const s = join_present([fmt_amount(i.amount), i.unit, i.name], " ");
	return i.note ? s + " (" + i.note + ")" : s;
}

function ingredient_item(i)
{
	const qty = join_present([fmt_amount(i.amount), i.unit], " ");
	const note = i.note ? h("span", { class: "note" },
				" (" + i.note + ")") : null;
	return h("li", {},
		h("span", { class: "amount" }, qty),
		h("span", {}, i.name, note));
}

function version_section(v)
{
	const facts = join_present([
		v.servings ? v.servings + " Portionen" : "",
		v.prep_minutes ? "Vorbereitung " + fmt_minutes(v.prep_minutes)
			       : "",
		v.cook_minutes ? "Kochen " + fmt_minutes(v.cook_minutes) : "",
	], " · ");
	return h("section", {},
		facts ? h("p", { class: "meta-line" }, facts) : null,
		v.intro ? h("p", { class: "intro" }, v.intro) : null,
		h("h2", {}, "Zutaten"),
		h("ul", { class: "ingredients" },
			(v.ingredients || []).map(ingredient_item)),
		h("h2", {}, "Zubereitung"),
		h("ol", { class: "steps" },
			(v.steps || []).map(s => h("li", {}, s.text))));
}

async function remove_recipe(id)
{
	if (!confirm("Rezept wirklich löschen?"))
		return;
	try {
		await API.delete_recipe(id);
		toast("Rezept gelöscht", false);
		navigate("#/");
	} catch (e) {
		toast(error_msg(e), true);
	}
}

/*
 * Re-fetch the recipe and redraw the detail view in place (no scroll
 * jump), e.g. after adding a note or a photo.
 */
async function refresh_detail(id, opts)
{
	const seq = ++render_seq;
	try {
		const r = await API.get_recipe(id);
		if (seq === render_seq)
			show(detail_el(r, opts || {}), true);
	} catch (e) {
		toast(error_msg(e), true);
	}
}

/*
 * Run an API call, then refresh. Errors go to the toast.
 */
async function mutate(id, fn, done_msg, opts)
{
	try {
		await fn();
		if (done_msg)
			toast(done_msg, false);
		await refresh_detail(id, opts);
	} catch (e) {
		toast(error_msg(e), true);
	}
}

function favorite_button(r)
{
	return h("button", { type: "button", class: "btn btn-icon fav",
			     "aria-label": "Favorit",
			     "aria-pressed": pressed(r.favorite),
			     onclick: (ev) => {
		ev.currentTarget.disabled = true;
		mutate(r.id, () => API.set_favorite(r.id, !r.favorite), "");
	} }, r.favorite ? "★" : "☆");
}

/* ---- photos ---- */

function photo_overlay(p)
{
	const close = () => {
		box.remove();
		document.removeEventListener("keydown", on_key);
	};
	const on_key = (ev) => {
		if (ev.key === "Escape")
			close();
	};
	const box = h("div", { class: "overlay", onclick: close },
		h("img", { src: p.url, alt: "" }),
		h("button", { type: "button", class: "btn-icon close",
			      "aria-label": "Schliessen" }, "✕"));
	document.addEventListener("keydown", on_key);
	document.body.append(box);
}

function photo_item(id, p)
{
	return h("figure", { class: "photo" },
		h("button", { type: "button", class: "thumb-btn",
			      "aria-label": "Foto öffnen",
			      onclick: () => photo_overlay(p) },
			h("img", { src: p.thumb_url, alt: "",
				   loading: "lazy" })),
		p.is_own_result ? h("figcaption", { class: "badge" },
					"Eigenes Ergebnis") : null,
		h("button", { type: "button", class: "del btn-danger",
			      "aria-label": "Foto löschen", onclick: () => {
			if (!confirm("Foto löschen?"))
				return;
			mutate(id, () => API.delete_photo(id, p.id),
			       "Foto gelöscht");
		} }, "✕"));
}

function photo_upload(id)
{
	const own = h("input", { type: "checkbox", name: "is_own_result" });
	const btn = h("button", { type: "button" }, "Foto");
	const file = h("input", { type: "file", accept: "image/*",
				  capture: "environment", class: "hidden",
				  "aria-label": "Foto wählen",
				  onchange: async (ev) => {
		const f = ev.target.files && ev.target.files[0];
		if (!f)
			return;
		btn.disabled = true;
		btn.textContent = "Lädt …";
		await mutate(id, () => API.upload_photo(id, f, own.checked),
			     "Foto gespeichert");
		btn.disabled = false;
		btn.textContent = "Foto";
		ev.target.value = "";
	} });
	btn.addEventListener("click", () => file.click());
	return h("div", { class: "upload" },
		btn, file,
		h("label", { class: "check" }, own,
			h("span", {}, "eigenes Ergebnis")));
}

function photo_section(r)
{
	const photos = r.photos || [];
	return h("section", { class: "photos-section" },
		photos.length ? h("div", { class: "photos" },
				  photos.map(p => photo_item(r.id, p))) : null,
		photo_upload(r.id));
}

/* ---- cook log ---- */

function newest_first(items, key)
{
	return items.slice().sort((a, b) => {
		if (a[key] === b[key])
			return b.id - a.id;
		return a[key] < b[key] ? 1 : -1;
	});
}

function delete_button(label, on_click)
{
	return h("button", { type: "button", class: "del btn-danger",
			     "aria-label": label, onclick: on_click }, "✕");
}

function cooklog_item(id, c)
{
	return h("li", { class: "entry" },
		h("div", { class: "entry-head" },
			h("span", { class: "date" }, fmt_date(c.cooked_on)),
			c.rating ? h("span", { class: "rating" },
				     stars_text(c.rating)) : null,
			delete_button("Eintrag löschen", () => {
				if (!confirm("Eintrag löschen?"))
					return;
				mutate(id, () => API.delete_cooklog(id, c.id),
				       "Eintrag gelöscht");
			})),
		c.comment ? h("p", { class: "comment" }, c.comment) : null);
}

function star_picker()
{
	let value = null;
	const btns = [];
	const draw = () => {
		btns.forEach((b, i) => {
			const on = value !== null && i < value;
			b.textContent = on ? "★" : "☆";
			b.setAttribute("aria-pressed", pressed(on));
		});
	};
	for (let i = 1; i <= RATING_MAX; i++)
		btns.push(h("button", { type: "button",
					"aria-label": i + " Sterne",
					onclick: () => {
			value = value === i ? null : i;
			draw();
		} }));
	draw();
	return { el: h("div", { class: "stars", role: "group",
				"aria-label": "Bewertung" }, btns),
		 read: () => value };
}

function cooklog_form(id)
{
	const date = h("input", { type: "date", name: "cooked_on",
				  value: today_iso(), required: true });
	const stars = star_picker();
	const comment = h("input", { name: "comment",
				     placeholder: "Kommentar" });
	const save = h("button", { type: "submit", class: "btn-primary" },
		       "Speichern");
	return h("form", { class: "entry-form", onsubmit: (ev) => {
		ev.preventDefault();
		save.disabled = true;
		mutate(id, () => API.add_cooklog(id, {
			cooked_on: date.value,
			rating: stars.read(),
			comment: comment.value.trim(),
		}), "Eingetragen");
	} },
		field("Datum", date),
		h("div", { class: "field" },
			h("span", { class: "field-label" }, "Bewertung"),
			stars.el),
		field("Kommentar", comment),
		h("div", { class: "actions" }, save));
}

function cooklog_section(r, open_form)
{
	const entries = newest_first(r.cook_log || [], "cooked_on");
	const form = cooklog_form(r.id);
	form.classList.toggle("hidden", !open_form);
	const add = h("button", { type: "button", onclick: () => {
		form.classList.toggle("hidden");
		if (!form.classList.contains("hidden"))
			form.scrollIntoView({ block: "nearest" });
	} }, "Eintragen");
	return h("section", {},
		h("div", { class: "section-head" },
			h("h2", {}, "Gekocht"), add),
		entries.length ? h("ul", { class: "entries" },
				   entries.map(c => cooklog_item(r.id, c)))
			       : null,
		form);
}

/* ---- notes ---- */

function note_item(id, n)
{
	return h("li", { class: "entry" },
		h("div", { class: "entry-head" },
			h("span", { class: "date" }, fmt_date(n.created_at)),
			delete_button("Notiz löschen", () => {
				if (!confirm("Notiz löschen?"))
					return;
				mutate(id, () => API.delete_note(id, n.id),
				       "Notiz gelöscht");
			})),
		h("p", { class: "comment" }, n.text));
}

function note_form(id)
{
	const ta = h("textarea", { name: "note", rows: 2,
				   placeholder: "Notiz", required: true,
				   "aria-label": "Notiz" });
	const save = h("button", { type: "submit", class: "btn-primary" },
		       "Speichern");
	return h("form", { class: "entry-form", onsubmit: (ev) => {
		ev.preventDefault();
		const text = ta.value.trim();
		if (text === "")
			return;
		save.disabled = true;
		mutate(id, () => API.add_note(id, text), "Gespeichert");
	} },
		ta,
		h("div", { class: "actions" }, save));
}

function notes_section(r)
{
	const notes = newest_first(r.notes || [], "created_at");
	return h("section", {},
		h("h2", {}, "Notizen"),
		notes.length ? h("ul", { class: "entries" },
				 notes.map(n => note_item(r.id, n))) : null,
		note_form(r.id));
}

/* ---- page ---- */

function detail_el(r, opts)
{
	let show_original = false;
	const title = h("h1", {}, r.own.title);
	const body = h("div", {}, version_section(r.own));
	const toggle = h("button", { type: "button", onclick: () => {
		show_original = !show_original;
		const v = show_original ? r.original : r.own;
		title.textContent = v.title;
		toggle.textContent = show_original ?
			"Eigene Version anzeigen" : "Original anzeigen";
		body.replaceChildren(version_section(v));
	} }, "Original anzeigen");
	const cat = r.category ? r.category.name : "";
	const tags = (r.tags || []).map(t => "#" + t).join(" ");
	const meta = join_present([cat, tags], " · ");
	const del = h("button", { type: "button", class: "btn-danger",
				  onclick: () => remove_recipe(r.id) },
		      "Löschen");
	const log = cooklog_section(r, opts.open_cooklog);
	const el = h("div", {},
		topbar(r.own.title, back_button("#/"), favorite_button(r)),
		h("main", {},
			title,
			meta ? h("p", { class: "meta-line" }, meta) : null,
			source_line(r.source),
			photo_section(r),
			h("div", { class: "actions" },
				h("a", { class: "btn btn-primary",
					 href: "#/cook/" + r.id }, "Kochen")),
			body,
			h("div", { class: "actions" },
				toggle,
				h("a", { class: "btn", href: "#/edit/" + r.id },
					"Bearbeiten"),
				del),
			log,
			notes_section(r)));
	if (opts.open_cooklog)
		setTimeout(() => log.scrollIntoView({ block: "start" }), 0);
	return el;
}

async function view_detail(id)
{
	const r = await API.get_recipe(id);
	const cooked = location.hash.endsWith(COOKED_FLAG);
	if (cooked)
		history.replaceState(null, "", "#/recipe/" + id);
	return detail_el(r, { open_cooklog: cooked });
}

/* ------------------------------------------------------------------ */
/* Form (new and edit)                                                 */
/* ------------------------------------------------------------------ */

async function save_recipe(id, input)
{
	const r = id ? await API.update_recipe(id, input)
		     : await API.create_recipe(input);
	toast("Gespeichert", false);
	navigate("#/recipe/" + (r && r.id ? r.id : id));
}

async function view_form(id)
{
	await load_taxonomy();
	const data = id ? recipe_to_input(await API.get_recipe(id))
			: empty_input();
	const back = id ? "#/recipe/" + id : "#/";
	const form = recipe_form(data, state.categories, {
		cancel_href: back,
		on_save: (input) => save_recipe(id, input),
	});
	return h("div", {},
		topbar(id ? "Rezept bearbeiten" : "Neues Rezept",
		       back_button(back)),
		h("main", {}, form));
}

/* ------------------------------------------------------------------ */
/* Import                                                              */
/* ------------------------------------------------------------------ */

async function view_import_route(query)
{
	await load_taxonomy();
	return view_import(query, { navigate: navigate,
				    categories: state.categories });
}

/* ------------------------------------------------------------------ */
/* Startup                                                             */
/* ------------------------------------------------------------------ */

function register_sw()
{
	if (!("serviceWorker" in navigator))
		return;
	navigator.serviceWorker.register("/sw.js").catch(() => {});
}

async function start()
{
	window.addEventListener(API.UNAUTHORIZED_EVENT, () => {
		if (state.user !== null) {
			state.user = null;
			navigate("#/login");
		}
	});
	window.addEventListener("hashchange", render);
	try {
		state.user = await API.me();
	} catch (e) {
		state.user = null;
	}
	if (!state.user && location.hash !== "#/login")
		location.hash = "#/login";
	render();
	register_sw();
}

start();
