/*
 * Cooking mode (#/cook/ID): one step at a time, ingredients to tick
 * off, portion stepper, timers from the step text, screen kept awake.
 * Tick state and current step live in sessionStorage until the user
 * taps "Fertig"; timers live only in this view and stop on leaving.
 *
 * app.js passes its DOM helpers in `ui` so this module stays free of
 * the router: ui = { h, navigate, toast, ingredient_text }.
 */

import * as API from "./api.js";
import {
	can_scale, scaled_ingredients, servings_stepper, load_servings,
	parse_timers, format_countdown,
} from "./scale.js";

const STORE_PREFIX = "cook:";
const COOK_ROUTE = /^#\/cook\/(\d+)$/;
const MAX_TIMERS = 3;
const TICK_MS = 250;
const BEEP_HZ = 880;
const BEEP_COUNT = 3;
const BEEP_MS = 200;
const BEEP_GAP_MS = 300;
const BEEP_GAIN = 0.3;
const VIBRATE_PATTERN = [200, 100, 200, 100, 200];

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
/* Alarm                                                               */
/* ------------------------------------------------------------------ */

/*
 * The AudioContext must be created in a user gesture (the tap on a
 * timer button), so it is opened on the first timer and reused.
 */
function open_audio(audio)
{
	const AC = window.AudioContext || window.webkitAudioContext;
	if (!AC)
		return null;
	try {
		const ctx = audio || new AC();
		if (ctx.state === "suspended")
			ctx.resume().catch(() => {});
		return ctx;
	} catch (e) {
		return null;
	}
}

function close_audio(audio)
{
	if (!audio)
		return;
	try {
		audio.close().catch(() => {});
	} catch (e) {
		/* already closed */
	}
}

/* 3 × 200 ms sine beeps. */
function beep(audio)
{
	if (!audio)
		return;
	try {
		for (let i = 0; i < BEEP_COUNT; i++) {
			const osc = audio.createOscillator();
			const gain = audio.createGain();
			osc.frequency.value = BEEP_HZ;
			gain.gain.value = BEEP_GAIN;
			osc.connect(gain);
			gain.connect(audio.destination);
			const t = audio.currentTime + i * BEEP_GAP_MS / 1000;
			osc.start(t);
			osc.stop(t + BEEP_MS / 1000);
		}
	} catch (e) {
		/* no sound */
	}
}

function vibrate()
{
	if (!navigator.vibrate)
		return;
	try {
		navigator.vibrate(VIBRATE_PATTERN);
	} catch (e) {
		/* not allowed */
	}
}

/* ------------------------------------------------------------------ */
/* Timer bar                                                           */
/* ------------------------------------------------------------------ */

/*
 * Sticky bar with up to MAX_TIMERS countdowns. on_change() runs when
 * a timer starts or is removed so the step buttons can follow.
 */
function timer_bar(h, on_change)
{
	const bar = h("div", { class: "timerbar hidden" });
	const timers = [];
	let tick = null;
	let audio = null;

	const update = () => {
		bar.classList.toggle("hidden", timers.length === 0);
		if (timers.length === 0 && tick) {
			clearInterval(tick);
			tick = null;
		}
		on_change();
	};

	const remove = (t) => {
		t.el.remove();
		timers.splice(timers.indexOf(t), 1);
		update();
	};

	const finish = (t) => {
		t.done = true;
		t.el.classList.add("done");
		t.time.textContent = format_countdown(0);
		beep(audio);
		vibrate();
	};

	const draw = () => {
		const now = Date.now();
		for (const t of timers) {
			if (t.done)
				continue;
			const left = Math.ceil((t.end - now) / 1000);
			t.time.textContent = format_countdown(left);
			if (left <= 0)
				finish(t);
		}
	};

	const add = (step, label, seconds) => {
		if (timers.length >= MAX_TIMERS)
			return false;
		audio = open_audio(audio);
		const time = h("span", { class: "timer-time" });
		const t = { end: Date.now() + seconds * 1000, done: false,
			    time: time };
		t.el = h("div", { class: "timer" },
			h("span", { class: "timer-label" },
				"Schritt " + step + " · " + label),
			time,
			h("button", { type: "button",
				      onclick: () => remove(t) }, "Stopp"));
		timers.push(t);
		bar.append(t.el);
		draw();
		if (!tick)
			tick = setInterval(draw, TICK_MS);
		update();
		return true;
	};

	const stop_all = () => {
		for (const t of timers)
			t.el.remove();
		timers.length = 0;
		update();
		close_audio(audio);
		audio = null;
	};

	return { el: bar, add: add, stop_all: stop_all,
		 full: () => timers.length >= MAX_TIMERS };
}

/* ------------------------------------------------------------------ */
/* Pieces                                                              */
/* ------------------------------------------------------------------ */

function fill_ingredients(ui, ul, id, rows, st)
{
	const h = ui.h;
	ul.replaceChildren(...rows.map((i, idx) =>
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

/* Stepper (when the version has a portion count) and tick list. */
function ingredient_block(ui, id, v, st)
{
	const h = ui.h;
	const ul = h("ul", { class: "checks" });
	const draw = (n) => fill_ingredients(ui, ul, id,
					     scaled_ingredients(v, n), st);
	draw(load_servings(id, v.servings));
	return [can_scale(v) ? servings_stepper(h, id, v, draw) : null, ul];
}

function timer_buttons(ui, box, step, text, bar)
{
	const h = ui.h;
	const found = parse_timers(text);
	box.replaceChildren();
	if (found.length === 0)
		return;
	box.append(h("span", { class: "timers-label" }, "Timer"),
		   ...found.map(t => h("button", { type: "button",
						    class: "btn-timer",
						    disabled: bar.full(),
						    onclick: () => {
			if (!bar.add(step, t.label, t.seconds))
				ui.toast("Höchstens " + MAX_TIMERS + " Timer",
					 true);
		} }, t.label)));
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
	const timers = h("div", { class: "timers" });
	const bar = timer_bar(h, () => timer_buttons(ui, timers, st.step + 1,
						   steps[st.step] || "", bar));
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
		timer_buttons(ui, timers, st.step + 1, steps[st.step] || "",
			      bar);
		for (const [k, li] of Array.from(all.children).entries())
			li.classList.toggle("current", k === st.step);
		prev.disabled = st.step === 0;
		next.disabled = st.step >= last;
	}
	go(st.step);

	if (leave)
		leave();
	const release = wake_lock();
	const cleanup = () => {
		window.removeEventListener("hashchange", on_hash);
		release();
		bar.stop_all();
		leave = null;
	};
	const on_hash = () => {
		if (!COOK_ROUTE.test(location.hash))
			cleanup();
	};
	window.addEventListener("hashchange", on_hash);
	leave = cleanup;

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
		bar.el,
		h("main", {},
			ings.length ? h("h2", {}, "Zutaten") : null,
			ings.length ? ingredient_block(ui, id, v, st) : null,
			h("section", { class: "step" }, counter, text, timers),
			steps.length > 1 ? all : null),
		h("div", { class: "cookbar" }, prev, next));
}
