/*
 * Cooking mode (#/cook/ID): one step at a time, ingredients to tick
 * off, screen kept awake. Tick state and current step live in
 * sessionStorage until the user taps "Fertig".
 *
 * app.js passes its DOM helpers in `ui` so this module stays free of
 * the router: ui = { h, navigate, ingredient_text }.
 */

import * as API from "./api.js";

const STORE_PREFIX = "cook:";
const COOK_ROUTE = /^#\/cook\/(\d+)$/;

/* Cleanup for the active cooking view, if any. */
let leave = null;

/* ------------------------------------------------------------------ */
/* Wake Lock                                                           */
/* ------------------------------------------------------------------ */

function wake_lock()
{
	let lock = null;
	const acquire = async () => {
		if (!("wakeLock" in navigator))
			return;
		try {
			lock = await navigator.wakeLock.request("screen");
		} catch (e) {
			lock = null;
		}
	};
	const release = () => {
		if (!lock)
			return;
		try {
			lock.release().catch(() => {});
		} catch (e) {
			/* already released */
		}
		lock = null;
	};
	const on_visible = () => {
		if (document.visibilityState === "visible")
			acquire();
	};
	document.addEventListener("visibilitychange", on_visible);
	acquire();
	return () => {
		document.removeEventListener("visibilitychange", on_visible);
		release();
	};
}

/* ------------------------------------------------------------------ */
/* Session state                                                       */
/* ------------------------------------------------------------------ */

function store_key(id)
{
	return STORE_PREFIX + id;
}

function load_state(id, n_ing)
{
	let st = null;
	try {
		st = JSON.parse(sessionStorage.getItem(store_key(id)));
	} catch (e) {
		st = null;
	}
	if (!st || !Array.isArray(st.checked))
		st = { checked: [], step: 0 };
	st.checked = Array.from({ length: n_ing }, (_, i) => !!st.checked[i]);
	st.step = Number.isInteger(st.step) ? st.step : 0;
	return st;
}

function save_state(id, st)
{
	try {
		sessionStorage.setItem(store_key(id), JSON.stringify(st));
	} catch (e) {
		/* storage full or blocked: keep going without it */
	}
}

function clear_state(id)
{
	try {
		sessionStorage.removeItem(store_key(id));
	} catch (e) {
		/* nothing to clear */
	}
}

/* ------------------------------------------------------------------ */
/* Pieces                                                              */
/* ------------------------------------------------------------------ */

function ingredient_list(ui, id, ings, st)
{
	const h = ui.h;
	return h("ul", { class: "checks" }, ings.map((i, idx) =>
		h("li", { class: st.checked[idx] ? "done" : "" },
			h("label", { class: "check" },
				h("input", { type: "checkbox",
					     checked: st.checked[idx],
					     onchange: (ev) => {
					const on = ev.target.checked;
					st.checked[idx] = on;
					save_state(id, st);
					ev.target.closest("li").classList
						.toggle("done", on);
				} }),
				h("span", {}, ui.ingredient_text(i))))));
}

function clamp(n, max)
{
	return Math.min(Math.max(n, 0), max);
}

/* ------------------------------------------------------------------ */
/* View                                                                */
/* ------------------------------------------------------------------ */

export async function view_cook(id, ui)
{
	const h = ui.h;
	const r = await API.get_recipe(id);
	const v = r.own;
	const steps = (v.steps || []).map(s => s.text);
	const ings = v.ingredients || [];
	const last = Math.max(steps.length - 1, 0);
	const st = load_state(id, ings.length);
	st.step = clamp(st.step, last);

	const counter = h("p", { class: "counter" });
	const text = h("p", { class: "step-text" });
	const all = h("ol", { class: "steps all-steps" }, steps.map((s, i) =>
		h("li", { onclick: () => go(i) }, s)));
	const prev = h("button", { type: "button", class: "btn-step",
				   onclick: () => go(st.step - 1) }, "Zurück");
	const next = h("button", { type: "button",
				   class: "btn-step btn-primary",
				   onclick: () => go(st.step + 1) }, "Weiter");

	function go(i)
	{
		st.step = clamp(i, last);
		save_state(id, st);
		counter.textContent = steps.length ?
			(st.step + 1) + " / " + steps.length : "";
		text.textContent = steps[st.step] || "";
		for (const [k, li] of Array.from(all.children).entries())
			li.classList.toggle("current", k === st.step);
		prev.disabled = st.step === 0;
		next.disabled = st.step >= last;
	}
	go(st.step);

	if (leave)
		leave();
	const release = wake_lock();
	const on_hash = () => {
		if (COOK_ROUTE.test(location.hash))
			return;
		window.removeEventListener("hashchange", on_hash);
		release();
		leave = null;
	};
	window.addEventListener("hashchange", on_hash);
	leave = () => {
		window.removeEventListener("hashchange", on_hash);
		release();
		leave = null;
	};

	const finish = () => {
		const log = confirm("Als gekocht eintragen?");
		clear_state(id);
		ui.navigate("#/recipe/" + id + (log ? "?cooked" : ""));
	};

	return h("div", { class: "cook" },
		h("header", { class: "topbar" },
			h("h1", {}, v.title),
			h("button", { type: "button", class: "btn-primary",
				      onclick: finish }, "Fertig")),
		h("main", {},
			ings.length ? h("h2", {}, "Zutaten") : null,
			ingredient_list(ui, id, ings, st),
			h("section", { class: "step" }, counter, text),
			steps.length > 1 ? all : null),
		h("div", { class: "cookbar" }, prev, next));
}
