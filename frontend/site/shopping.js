/*
 * Shopping list (#/shopping) and pantry (#/pantry).
 *
 * Open items come first, ticked ones struck through below. A tap on
 * a line toggles it (PUT /checked), «✕» deletes it. «Nach To Do»
 * pushes the open items to Microsoft To Do when the server has it
 * configured. Pantry names are skipped when a recipe is put on the
 * list; they are edited on their own page.
 */

import * as API from "./api.js";
import { h, toast, error_msg, back_button, topbar } from "./form.js";
import { scale_amount } from "./scale.js";

const TODO_LOGIN_CMD =
	"docker compose exec api python -m app.cli todo-login";

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

function join_present(parts, sep)
{
	return parts.filter(p => p !== "" && p !== null &&
			     p !== undefined).join(sep);
}

/* Open items in list order, then the ticked ones. */
function sort_items(items)
{
	return items.slice().sort((a, b) => {
		if (a.checked !== b.checked)
			return a.checked ? 1 : -1;
		return a.id - b.id;
	});
}

function del_button(label, on_click)
{
	return h("button", { type: "button", class: "del btn-danger",
			     "aria-label": label, onclick: on_click }, "✕");
}

function plus_button()
{
	return h("button", { type: "submit", class: "btn-primary add",
			     "aria-label": "Hinzufügen" }, "+");
}

/* "12,5" -> "12.5", "" -> null */
function decimal_or_null(s)
{
	const t = String(s).trim().replace(",", ".");
	return t === "" ? null : t;
}

/* ------------------------------------------------------------------ */
/* Shopping list                                                       */
/* ------------------------------------------------------------------ */

function item_line(i, on_toggle, on_delete)
{
	const box = h("input", { type: "checkbox", checked: i.checked,
				 "aria-label": i.name,
				 onchange: () => on_toggle(i, box.checked) });
	/* factor 1: only the fraction symbols */
	const qty = join_present([scale_amount(i.amount, 1), i.unit], " ");
	return h("li", { class: i.checked ? "item done" : "item" },
		h("label", { class: "check" }, box,
			h("span", { class: "text" },
				qty ? h("span", { class: "qty" }, qty + " ")
				    : null,
				i.name,
				i.note ? h("small", { class: "note" },
					   " " + i.note) : null)),
		del_button("Entfernen", () => on_delete(i)));
}

/*
 * Keeps the items in memory and redraws after every change; the
 * server answer wins, an error reverts the change.
 */
function shopping_list()
{
	let items = [];
	const ul = h("ul", { class: "shop" });
	const draw = () => {
		ul.replaceChildren(
			...sort_items(items).map(i => item_line(i, toggle,
								remove)));
		if (items.length === 0)
			ul.append(h("li", { class: "empty" }, "Liste leer"));
	};
	const toggle = async (i, checked) => {
		i.checked = checked;
		draw();
		try {
			const r = await API.set_shopping_checked(i.id, checked);
			Object.assign(i, r);
		} catch (e) {
			i.checked = !checked;
			toast(error_msg(e), true);
		}
		draw();
	};
	const remove = async (i) => {
		try {
			await API.remove_shopping(i.id);
			items = items.filter(x => x.id !== i.id);
			draw();
		} catch (e) {
			toast(error_msg(e), true);
		}
	};
	const reload = async () => {
		items = await API.list_shopping();
		draw();
	};
	const add = (i) => {
		items.push(i);
		draw();
	};
	const clear_checked = async () => {
		if (!items.some(i => i.checked))
			return;
		try {
			await API.clear_checked_shopping();
			items = items.filter(i => !i.checked);
			draw();
		} catch (e) {
			toast(error_msg(e), true);
		}
	};
	return { el: ul, reload: reload, add: add,
		 clear_checked: clear_checked };
}

/*
 * «Zutat» + «+» at the bottom; «Menge» opens a row for amount and
 * unit.
 */
function add_form(list)
{
	const name = h("input", { name: "name", placeholder: "Zutat",
				  "aria-label": "Zutat", required: true,
				  autocomplete: "off" });
	const amount = h("input", { name: "amount", placeholder: "Menge",
				    "aria-label": "Menge",
				    inputmode: "decimal", class: "narrow" });
	const unit = h("input", { name: "unit", placeholder: "Einheit",
				  "aria-label": "Einheit", class: "narrow" });
	const more = h("div", { class: "row hidden" }, amount, unit);
	const toggle = h("button", { type: "button", class: "btn-link",
				     "aria-expanded": "false", onclick: () => {
		const open = more.classList.toggle("hidden");
		toggle.setAttribute("aria-expanded", open ? "false" : "true");
		if (!open)
			amount.focus();
	} }, "Menge");
	const plus = plus_button();
	const reset = () => {
		name.value = "";
		amount.value = "";
		unit.value = "";
		more.classList.add("hidden");
		toggle.setAttribute("aria-expanded", "false");
	};
	return h("form", { class: "shop-add", onsubmit: async (ev) => {
		ev.preventDefault();
		const n = name.value.trim();
		if (n === "")
			return;
		plus.disabled = true;
		try {
			list.add(await API.add_shopping({
				name: n,
				unit: unit.value.trim(),
				amount: decimal_or_null(amount.value),
				note: "",
			}));
			reset();
			name.focus();
		} catch (e) {
			toast(error_msg(e), true);
		} finally {
			plus.disabled = false;
		}
	} },
		h("div", { class: "row" }, name, toggle, plus),
		more);
}

function push_result(r)
{
	return r.added + " hinzugefügt, " + r.skipped + " vorhanden";
}

/*
 * «Nach To Do», only when the server knows a To Do list. Without a
 * login it stays visible but inactive and a tap names the command.
 */
function todo_button(status)
{
	if (!status || !status.configured)
		return null;
	const btn = h("button", { type: "button" }, "Nach To Do");
	if (!status.logged_in) {
		btn.setAttribute("aria-disabled", "true");
		btn.addEventListener("click",
				    () => toast(TODO_LOGIN_CMD, true));
		return [btn, h("span", { class: "hint" }, "Anmeldung fehlt")];
	}
	btn.addEventListener("click", async () => {
		btn.disabled = true;
		try {
			toast(push_result(await API.todo_push()), false);
		} catch (e) {
			toast(error_msg(e), true);
		} finally {
			btn.disabled = false;
		}
	});
	return btn;
}

async function load_todo_status()
{
	try {
		return await API.todo_status();
	} catch (e) {
		return null;
	}
}

export async function view_shopping()
{
	const list = shopping_list();
	const [status] = await Promise.all([load_todo_status(),
					    list.reload()]);
	const clear = h("button", { type: "button",
				    onclick: list.clear_checked },
			"Erledigte löschen");
	return h("div", {},
		topbar("Einkaufsliste", back_button("#/"),
		       h("a", { class: "btn", href: "#/pantry" }, "Vorräte")),
		h("main", {},
			h("div", { class: "btn-row" }, clear,
				todo_button(status)),
			list.el,
			add_form(list)));
}

/* ------------------------------------------------------------------ */
/* Pantry                                                              */
/* ------------------------------------------------------------------ */

function pantry_line(p, on_delete)
{
	return h("li", { class: "item" },
		h("span", { class: "text" }, p.name),
		del_button("Entfernen", () => on_delete(p)));
}

export async function view_pantry()
{
	let items = await API.list_pantry();
	const ul = h("ul", { class: "shop pantry" });
	const draw = () => {
		ul.replaceChildren(...items.map(p => pantry_line(p, remove)));
		if (items.length === 0)
			ul.append(h("li", { class: "empty" },
				     "Keine Vorräte"));
	};
	const remove = async (p) => {
		try {
			await API.remove_pantry(p.id);
			items = items.filter(x => x.id !== p.id);
			draw();
		} catch (e) {
			toast(error_msg(e), true);
		}
	};
	const name = h("input", { name: "name", placeholder: "Zutat",
				  "aria-label": "Zutat", required: true,
				  autocomplete: "off" });
	const plus = plus_button();
	const form = h("form", { class: "shop-add", onsubmit: async (ev) => {
		ev.preventDefault();
		const n = name.value.trim();
		if (n === "")
			return;
		plus.disabled = true;
		try {
			items.push(await API.add_pantry(n));
			draw();
			name.value = "";
			name.focus();
		} catch (e) {
			toast(error_msg(e), true);
		} finally {
			plus.disabled = false;
		}
	} }, h("div", { class: "row" }, name, plus));
	draw();
	return h("div", {},
		topbar("Vorräte", back_button("#/shopping")),
		h("main", {}, ul, form));
}
