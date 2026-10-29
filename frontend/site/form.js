/*
 * Shared DOM helpers and the recipe form, used by app.js (new/edit)
 * and import.js (preview). All user text goes through h() /
 * textContent, never innerHTML.
 */

import * as API from "./api.js";

const TOAST_MS = 4000;
const NEW_CATEGORY = "__new__";
const SOURCE_KINDS = [
	["url", "Link"],
	["book", "Buch"],
	["none", "Keine"],
];
const NUTRITION_FIELDS = [
	["kcal", "kcal"],
	["protein_g", "Eiweiss (g)"],
	["carbs_g", "Kohlenhydrate (g)"],
	["fat_g", "Fett (g)"],
];

let toast_timer = null;

/* ------------------------------------------------------------------ */
/* DOM helpers                                                         */
/* ------------------------------------------------------------------ */

/*
 * h(tag, attrs, ...children): create an element. Attributes starting
 * with "on" become event listeners, children may be nodes, strings,
 * arrays or null.
 */
export function h(tag, attrs, ...children)
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

export function append(el, children)
{
	for (const c of children.flat(Infinity)) {
		if (c === null || c === undefined || c === false)
			continue;
		el.append(c instanceof Node ? c : String(c));
	}
}

export function toast(msg, is_error)
{
	const t = document.getElementById("toast");
	t.textContent = msg;
	t.className = is_error ? "error" : "";
	t.hidden = false;
	clearTimeout(toast_timer);
	toast_timer = setTimeout(() => { t.hidden = true; }, TOAST_MS);
}

export function error_msg(e)
{
	return e && e.message ? e.message : "Unbekannter Fehler";
}

export function field(label, input)
{
	return h("label", {}, h("span", {}, label), input);
}

export function back_button(href)
{
	return h("a", { class: "btn btn-icon", href: href,
			"aria-label": "Zurück" }, "‹");
}

export function topbar(title, ...actions)
{
	return h("header", { class: "topbar" },
		h("h1", {}, title), ...actions);
}

export function str(v)
{
	return v === null || v === undefined ? "" : String(v);
}

/*
 * Amounts come back as decimal strings ("250.000"); drop the noise.
 */
export function fmt_amount(a)
{
	if (a === null || a === undefined || a === "")
		return "";
	const s = String(a);
	if (!/^-?\d+\.\d+$/.test(s))
		return s;
	return s.replace(/0+$/, "").replace(/\.$/, "");
}

export function split_csv(s)
{
	return s.split(",").map(x => x.trim()).filter(x => x !== "");
}

/* ------------------------------------------------------------------ */
/* Form data                                                           */
/* ------------------------------------------------------------------ */

export function empty_input()
{
	return {
		category_id: null,
		tags: [],
		favorite: false,
		source: { kind: "none", url: "", book: "", page: null },
		version: {
			title: "", intro: "", servings: null,
			prep_minutes: null, cook_minutes: null,
			nutrition: empty_nutrition(),
			ingredients: [], steps: [],
		},
	};
}

export function empty_nutrition()
{
	return { kcal: null, protein_g: null, carbs_g: null, fat_g: null };
}

export function recipe_to_input(r)
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

/* ------------------------------------------------------------------ */
/* Rows                                                                */
/* ------------------------------------------------------------------ */

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

export function ingredient_row(i)
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

export function step_row(s)
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

export function read_ingredients(box)
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

export function read_steps(box)
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

/* "12,5" -> "12.5", "" -> null; the server validates the number. */
function decimal_or_null(s)
{
	const t = String(s).trim().replace(",", ".");
	return t === "" ? null : t;
}

/* ------------------------------------------------------------------ */
/* Fields                                                              */
/* ------------------------------------------------------------------ */

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

/*
 * Collapsible "Nährwerte pro Portion", open when a value is set.
 * read() gives the four values as strings or null.
 */
function nutrition_fields(n)
{
	const inputs = NUTRITION_FIELDS.map(([key, label]) => [label,
		h("input", { name: key, inputmode: "decimal",
			     value: fmt_amount(n[key]) })]);
	const has = inputs.some(([, i]) => i.value !== "");
	const row = (pairs) => h("div", { class: "row" },
				 pairs.map(([label, i]) => field(label, i)));
	const el = h("details", { class: "nutrition", open: has },
		h("summary", {}, "Nährwerte pro Portion"),
		row(inputs.slice(0, 2)), row(inputs.slice(2)));
	const read = () => Object.fromEntries(NUTRITION_FIELDS.map(
		([key], k) => [key, decimal_or_null(inputs[k][1].value)]));
	return { el: el, read: read };
}

function category_options(cats, selected, empty_label)
{
	const opts = [h("option", { value: "" }, empty_label)];
	const sel = String(selected);
	for (const c of cats)
		opts.push(h("option", { value: c.id,
					selected: String(c.id) === sel },
				c.name));
	opts.push(h("option", { value: NEW_CATEGORY }, "+ neue Kategorie …"));
	return opts;
}

/*
 * cats is the shared category list; a newly created category is
 * pushed onto it.
 */
function category_field(cats, selected)
{
	const new_name = h("input", { name: "new_category",
				      placeholder: "Name der Kategorie" });
	const new_box = h("div", { class: "hidden" },
		field("Neue Kategorie", new_name));
	const sel = h("select", { name: "category", onchange: () => {
		new_box.classList.toggle("hidden", sel.value !== NEW_CATEGORY);
		if (sel.value === NEW_CATEGORY)
			new_name.focus();
	} }, category_options(cats, selected, "– keine –"));
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
		const existing = cats.find(
			c => c.name.toLowerCase() === name.toLowerCase());
		if (existing)
			return existing.id;
		const c = await API.create_category(name);
		cats.push(c);
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
	return { box: box, add: add };
}

function split_lines(text)
{
	return text.split("\n").map(x => x.trim()).filter(x => x !== "");
}

/*
 * "Zutaten einfügen": a textarea for pasted ingredient lines (one per
 * line). The lines go to /api/import/ingredients and come back as
 * rows appended to `box`.
 */
function paste_box(box)
{
	const ta = h("textarea", { name: "paste", rows: 6,
				   placeholder: "eine Zutat pro Zeile",
				   "aria-label": "Zutaten einfügen" });
	const take = h("button", { type: "button", class: "btn-primary" },
		       "Übernehmen");
	const panel = h("div", { class: "paste hidden" }, ta,
		h("div", { class: "btn-row" }, take));
	const toggle = h("button", { type: "button", onclick: () => {
		panel.classList.toggle("hidden");
		if (!panel.classList.contains("hidden"))
			ta.focus();
	} }, "Zutaten einfügen");
	take.addEventListener("click", async () => {
		const lines = split_lines(ta.value);
		if (lines.length === 0)
			return;
		take.disabled = true;
		try {
			const items = await API.parse_ingredients(lines);
			for (const i of items)
				box.append(ingredient_row(i));
			ta.value = "";
			panel.classList.add("hidden");
		} catch (e) {
			toast(error_msg(e), true);
		} finally {
			take.disabled = false;
		}
	});
	return { toggle: toggle, el: panel };
}

/* ------------------------------------------------------------------ */
/* Form                                                                */
/* ------------------------------------------------------------------ */

/*
 * Build the recipe form from a RecipeInput-like object. opts:
 *   cancel_href  target of "Abbrechen"
 *   on_save(input)  async; receives the RecipeInput read from the
 *                   form. An error is shown as toast and re-enables
 *                   the save button.
 */
export function recipe_form(data, cats, opts)
{
	const v = data.version;

	const title = h("input", { name: "title", required: true,
				   value: v.title || "" });
	const cat = category_field(cats, data.category_id);
	const tags = h("input", { name: "tags", placeholder: "vegi, schnell",
				  autocapitalize: "none",
				  value: data.tags.join(", ") });
	const fav = h("input", { type: "checkbox", name: "favorite",
				 checked: data.favorite });
	const src = source_fields(data.source);
	const servings = number_input("servings", v.servings);
	const prep = number_input("prep_minutes", v.prep_minutes);
	const cook = number_input("cook_minutes", v.cook_minutes);
	const nutrition = nutrition_fields(v.nutrition || empty_nutrition());
	const intro = h("textarea", { name: "intro", rows: 3 }, v.intro || "");
	const ings = list_editor(v.ingredients || [], ingredient_row,
				 "+ Zutat");
	const paste = paste_box(ings.box);
	const steps = list_editor(v.steps || [], step_row, "+ Schritt");
	const save = h("button", { type: "submit", class: "btn-primary" },
		       "Speichern");

	const read = async () => ({
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
			nutrition: nutrition.read(),
			ingredients: read_ingredients(ings.box),
			steps: read_steps(steps.box),
		},
	});

	return h("form", { onsubmit: async (ev) => {
		ev.preventDefault();
		save.disabled = true;
		try {
			await opts.on_save(await read());
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
		nutrition.el,
		field("Einleitung", intro),
		h("h2", {}, "Zutaten"),
		ings.box,
		h("div", { class: "btn-row" }, ings.add, paste.toggle),
		paste.el,
		h("h2", {}, "Zubereitung"),
		steps.box,
		h("div", { class: "btn-row" }, steps.add),
		h("div", { class: "actions" },
			h("a", { class: "btn", href: opts.cancel_href },
				"Abbrechen"),
			save));
}
