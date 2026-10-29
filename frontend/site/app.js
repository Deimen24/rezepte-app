/*
 * Recipe app: hash router and views. No framework, no build step.
 *
 * Routes: #/login, #/ (list), #/recipe/ID, #/new, #/edit/ID.
 * All user text is rendered through h() / textContent, never innerHTML.
 */

import * as API from "./api.js";

const TOAST_MS = 4000;
const DEBOUNCE_MS = 300;
const LOADING_DELAY_MS = 150;
const NEW_CATEGORY = "__new__";
const SOURCE_KINDS = [
	["url", "Link"],
	["book", "Buch"],
	["none", "Keine"],
];

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
	[/^#\/recipe\/(\d+)$/, view_detail],
	[/^#\/new$/, view_form],
	[/^#\/edit\/(\d+)$/, view_form],
];

let render_seq = 0;
let toast_timer = null;

/* ------------------------------------------------------------------ */
/* DOM helpers                                                         */
/* ------------------------------------------------------------------ */

/*
 * h(tag, attrs, ...children): create an element. Attributes starting
 * with "on" become event listeners, children may be nodes, strings,
 * arrays or null.
 */
function h(tag, attrs, ...children)
{
	const el = document.createElement(tag);
	for (const [k, v] of Object.entries(attrs || {})) {
		if (k.startsWith("on") && typeof v === "function")
			el.addEventListener(k.slice(2), v);
		else if (k === "class")
			el.className = v;
		else if (v === true)
			el.setAttribute(k, "");
		else if (v !== false && v !== null && v !== undefined)
			el.setAttribute(k, v);
	}
	append(el, children);
	return el;
}

function append(el, children)
{
	for (const c of children.flat(Infinity)) {
		if (c === null || c === undefined || c === false)
			continue;
		el.append(c instanceof Node ? c : String(c));
	}
}

function show(el)
{
	const app = document.getElementById("app");
	app.replaceChildren(el);
	window.scrollTo(0, 0);
}

function toast(msg, is_error)
{
	const t = document.getElementById("toast");
	t.textContent = msg;
	t.className = is_error ? "error" : "";
	t.hidden = false;
	clearTimeout(toast_timer);
	toast_timer = setTimeout(() => { t.hidden = true; }, TOAST_MS);
}

function error_msg(e)
{
	return e && e.message ? e.message : "Unbekannter Fehler";
}

function debounce(fn, ms)
{
	let timer = null;
	return (...args) => {
		clearTimeout(timer);
		timer = setTimeout(() => fn(...args), ms);
	};
}

function field(label, input)
{
	return h("label", {}, h("span", {}, label), input);
}

function back_button(href)
{
	return h("a", { class: "btn btn-icon", href: href,
			"aria-label": "Zurück" }, "‹");
}

function topbar(title, ...actions)
{
	return h("header", { class: "topbar" },
		h("h1", {}, title), ...actions);
}

/* ------------------------------------------------------------------ */
/* Formatting                                                          */
/* ------------------------------------------------------------------ */

/*
 * Amounts come back as decimal strings ("250.000"); drop the noise.
 */
function fmt_amount(a)
{
	if (a === null || a === undefined || a === "")
		return "";
	const s = String(a);
	if (!/^-?\d+(\.\d+)?$/.test(s))
		return s;
	return s.replace(/\.?0+$/, "").replace(/\.(\d*[1-9])0+$/, ".$1");
}

function fmt_minutes(n)
{
	return n === null || n === undefined ? "" : n + " Min.";
}

function str(v)
{
	return v === null || v === undefined ? "" : String(v);
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

function category_options(selected, with_new, empty_label)
{
	const opts = [h("option", { value: "" }, empty_label)];
	const sel = String(selected);
	for (const c of state.categories)
		opts.push(h("option", { value: c.id,
					selected: String(c.id) === sel },
				c.name));
	if (with_new)
		opts.push(h("option", { value: NEW_CATEGORY },
				"+ neue Kategorie …"));
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

function split_csv(s)
{
	return s.split(",").map(x => x.trim()).filter(x => x !== "");
}

function star()
{
	return h("span", { class: "star", "aria-label": "Favorit" }, "★");
}

function recipe_card(r)
{
	const cat = r.category ? r.category.name : "";
	const tags = (r.tags || []).map(t => "#" + t).join(" ");
	return h("li", {},
		h("a", { class: "card", href: "#/recipe/" + r.id },
			h("div", { class: "title" },
				r.favorite ? star() : null,
				h("span", {}, r.title)),
			join_present([cat, tags], " · ") ?
				h("div", { class: "meta" },
					join_present([cat, tags], " · ")) :
				null));
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
	} }, category_options(filter.category, false, "Alle Kategorien"));
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
			h("button", { type: "button", class: "btn-link",
				      onclick: logout }, "Abmelden")),
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

async function view_detail(id)
{
	const r = await API.get_recipe(id);
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
	const meta = join_present([r.favorite ? "★ Favorit" : "",
				   cat, tags], " · ");
	const del = h("button", { type: "button", class: "btn-danger",
				  onclick: () => remove_recipe(r.id) },
		      "Löschen");
	return h("div", {},
		topbar(r.own.title, back_button("#/")),
		h("main", {},
			title,
			meta ? h("p", { class: "meta-line" }, meta) : null,
			source_line(r.source),
			body,
			h("div", { class: "actions" },
				toggle,
				h("a", { class: "btn", href: "#/edit/" + r.id },
					"Bearbeiten"),
				del)));
}

/* ------------------------------------------------------------------ */
/* Form (new and edit)                                                 */
/* ------------------------------------------------------------------ */

function empty_input()
{
	return {
		category_id: null,
		tags: [],
		favorite: false,
		source: { kind: "none", url: "", book: "", page: null },
		version: {
			title: "", intro: "", servings: null,
			prep_minutes: null, cook_minutes: null,
			ingredients: [], steps: [],
		},
	};
}

function recipe_to_input(r)
{
	return {
		category_id: r.category ? r.category.id : null,
		tags: r.tags || [],
		favorite: !!r.favorite,
		source: r.source || { kind: "none", url: "", book: "",
				      page: null },
		version: r.own,
	};
}

function move_item(item, dir)
{
	const sib = dir < 0 ? item.previousElementSibling
			    : item.nextElementSibling;
	if (!sib)
		return;
	if (dir < 0)
		sib.before(item);
	else
		sib.after(item);
}

function item_controls(item)
{
	return h("div", { class: "ctl" },
		h("button", { type: "button", "aria-label": "Nach oben",
			      onclick: () => move_item(item, -1) }, "↑"),
		h("button", { type: "button", "aria-label": "Nach unten",
			      onclick: () => move_item(item, 1) }, "↓"),
		h("button", { type: "button", "aria-label": "Entfernen",
			      class: "btn-danger",
			      onclick: () => item.remove() }, "✕"));
}

function text_input(f, label, value, cls)
{
	return h("input", { class: cls, "data-f": f, placeholder: label,
			    "aria-label": label, value: str(value) });
}

function ingredient_row(i)
{
	const item = h("div", { class: "ing-item" });
	const amount = text_input("amount", "Menge", fmt_amount(i.amount),
				  "narrow");
	amount.setAttribute("inputmode", "decimal");
	append(item, [
		h("div", { class: "row" },
			amount,
			text_input("unit", "Einheit", i.unit, "narrow"),
			text_input("name", "Zutat", i.name, "wide")),
		h("div", { class: "row" },
			text_input("note", "Notiz", i.note, ""),
			item_controls(item)),
	]);
	return item;
}

function step_row(s)
{
	const item = h("div", { class: "step-item" });
	const ta = h("textarea", { "data-f": "text", rows: 3,
				   placeholder: "Schritt",
				   "aria-label": "Schritt" }, str(s.text));
	append(item, [h("div", { class: "row" }, ta, item_controls(item))]);
	return item;
}

function read_field(item, name)
{
	return item.querySelector("[data-f=\"" + name + "\"]").value.trim();
}

function read_ingredients(box)
{
	const out = [];
	for (const item of box.children) {
		const name = read_field(item, "name");
		if (name === "")
			continue;
		const amount = read_field(item, "amount").replace(",", ".");
		out.push({
			amount: amount === "" ? null : amount,
			unit: read_field(item, "unit"),
			name: name,
			note: read_field(item, "note"),
		});
	}
	return out;
}

function read_steps(box)
{
	const out = [];
	for (const item of box.children) {
		const text = read_field(item, "text");
		if (text !== "")
			out.push({ text: text });
	}
	return out;
}

function int_or_null(s)
{
	const t = String(s).trim();
	return t === "" ? null : parseInt(t, 10);
}

function number_input(name, value, extra)
{
	return h("input", Object.assign({ name: name, type: "number",
					  min: 0, step: 1, inputmode: "numeric",
					  value: str(value) }, extra || {}));
}

function source_fields(src)
{
	const url = h("input", { name: "source_url", type: "url",
				 placeholder: "https://…",
				 inputmode: "url", value: src.url || "" });
	const book = h("input", { name: "source_book",
				  placeholder: "Buchtitel",
				  value: src.book || "" });
	const page = h("input", { name: "source_page", placeholder: "Seite",
				  inputmode: "numeric", value: str(src.page) });
	const url_box = h("div", {}, field("Link", url));
	const book_box = h("div", { class: "row" },
		h("div", { class: "wide" }, field("Buch", book)),
		h("div", { class: "narrow" }, field("Seite", page)));
	const update = (kind) => {
		url_box.classList.toggle("hidden", kind !== "url");
		book_box.classList.toggle("hidden", kind !== "book");
	};
	const radios = SOURCE_KINDS.map(([val, label]) =>
		h("label", { class: "check" },
			h("input", { type: "radio", name: "source_kind",
				     value: val, checked: src.kind === val,
				     onchange: () => update(val) }),
			h("span", {}, label)));
	update(src.kind);
	const read = () => {
		const kind = radios.map(l => l.firstChild)
				   .find(r => r.checked).value;
		const p = page.value.trim();
		return {
			kind: kind,
			url: kind === "url" ? url.value.trim() : "",
			book: kind === "book" ? book.value.trim() : "",
			page: kind === "book" && p !== "" ? p : null,
		};
	};
	const el = h("fieldset", {},
		h("legend", {}, "Quelle"),
		h("div", { class: "radio-row" }, radios),
		url_box, book_box);
	return { el: el, read: read };
}

function category_field(selected)
{
	const new_name = h("input", { name: "new_category",
				      placeholder: "Name der Kategorie" });
	const new_box = h("div", { class: "hidden" },
		field("Neue Kategorie", new_name));
	const sel = h("select", { name: "category", onchange: () => {
		new_box.classList.toggle("hidden", sel.value !== NEW_CATEGORY);
		if (sel.value === NEW_CATEGORY)
			new_name.focus();
	} }, category_options(selected, true, "– keine –"));
	const el = h("div", {}, field("Kategorie", sel), new_box);
	/*
	 * Resolve the category id, creating a new category first when
	 * the user asked for one.
	 */
	const resolve = async () => {
		if (sel.value === "")
			return null;
		if (sel.value !== NEW_CATEGORY)
			return parseInt(sel.value, 10);
		const name = new_name.value.trim();
		if (name === "")
			throw new Error("Name der neuen Kategorie fehlt");
		const existing = state.categories.find(
			c => c.name.toLowerCase() === name.toLowerCase());
		if (existing)
			return existing.id;
		const c = await API.create_category(name);
		state.categories.push(c);
		return c.id;
	};
	return { el: el, resolve: resolve };
}

function list_editor(items, make_row, add_label)
{
	const box = h("div", {}, items.map(make_row));
	const add = h("button", { type: "button", onclick: () => {
		const row = make_row({});
		box.append(row);
		row.querySelector("input, textarea").focus();
	} }, add_label);
	return { box: box, el: h("div", {}, box, add) };
}

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
	const v = data.version;

	const title = h("input", { name: "title", required: true,
				   value: v.title || "" });
	const cat = category_field(data.category_id);
	const tags = h("input", { name: "tags", placeholder: "vegi, schnell",
				  autocapitalize: "none",
				  value: data.tags.join(", ") });
	const fav = h("input", { type: "checkbox", name: "favorite",
				 checked: data.favorite });
	const src = source_fields(data.source);
	const servings = number_input("servings", v.servings);
	const prep = number_input("prep_minutes", v.prep_minutes);
	const cook = number_input("cook_minutes", v.cook_minutes);
	const intro = h("textarea", { name: "intro", rows: 3 }, v.intro || "");
	const ings = list_editor(v.ingredients || [], ingredient_row,
				 "+ Zutat");
	const steps = list_editor(v.steps || [], step_row, "+ Schritt");
	const save = h("button", { type: "submit", class: "btn-primary" },
		       "Speichern");

	const form = h("form", { onsubmit: async (ev) => {
		ev.preventDefault();
		save.disabled = true;
		try {
			await save_recipe(id, {
				category_id: await cat.resolve(),
				tags: split_csv(tags.value),
				favorite: fav.checked,
				source: src.read(),
				version: {
					title: title.value.trim(),
					intro: intro.value.trim(),
					servings: int_or_null(servings.value),
					prep_minutes: int_or_null(prep.value),
					cook_minutes: int_or_null(cook.value),
					ingredients: read_ingredients(ings.box),
					steps: read_steps(steps.box),
				},
			});
		} catch (e) {
			toast(error_msg(e), true);
			save.disabled = false;
		}
	} },
		field("Titel", title),
		cat.el,
		field("Schlagworte (durch Komma getrennt)", tags),
		h("label", { class: "check" }, fav, h("span", {}, "Favorit")),
		src.el,
		h("div", { class: "row bottom" },
			field("Portionen", servings),
			field("Vorbereitung (Min.)", prep),
			field("Kochen (Min.)", cook)),
		field("Einleitung", intro),
		h("h2", {}, "Zutaten"), ings.el,
		h("h2", {}, "Zubereitung"), steps.el,
		h("div", { class: "actions" },
			h("a", { class: "btn",
				 href: id ? "#/recipe/" + id : "#/" },
				"Abbrechen"),
			save));
	return h("div", {},
		topbar(id ? "Rezept bearbeiten" : "Neues Rezept",
		       back_button(id ? "#/recipe/" + id : "#/")),
		h("main", {}, form));
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
