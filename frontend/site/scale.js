/*
 * Portion scaling, timer detection and the shared servings stepper.
 * The pure functions have no DOM dependency so node can test them;
 * the stepper takes h() from the caller.
 */

const FRACTIONS = [
	[0.25, "¼"], [0.333, "⅓"], [0.5, "½"], [0.667, "⅔"], [0.75, "¾"],
];
const FRACTION_EPS = 0.01;
const SERVINGS_MIN = 1;
const SERVINGS_MAX = 99;
const STORE_PREFIX = "servings:";
const MAX_TIMERS_PER_STEP = 3;

/* ------------------------------------------------------------------ */
/* Amounts                                                             */
/* ------------------------------------------------------------------ */

function strip_zeros(s)
{
	return s.includes(".") ? s.replace(/0+$/, "").replace(/\.$/, "") : s;
}

/*
 * "250.000" * 0.5 -> "125", "1.5" * 0.5 -> "¾", 0.333 -> "⅓".
 * Non-numeric text comes back unchanged, null as "".
 */
export function scale_amount(amount_str, factor)
{
	if (amount_str === null || amount_str === undefined)
		return "";
	const raw = String(amount_str).trim();
	const n = parseFloat(raw.replace(",", "."));
	if (raw === "" || !isFinite(n))
		return raw;
	const v = Math.round(n * factor * 1000) / 1000;
	const whole = Math.floor(v);
	const frac = v - whole;
	if (frac < FRACTION_EPS)
		return String(whole);
	for (const [val, sym] of FRACTIONS)
		if (Math.abs(frac - val) < FRACTION_EPS)
			return whole ? whole + sym : sym;
	return strip_zeros(v.toFixed(3));
}

export function format_servings(n)
{
	return n === 1 ? "1 Portion" : n + " Portionen";
}

export function can_scale(version)
{
	return Number.isInteger(version.servings) && version.servings > 0;
}

/*
 * Ingredient rows with amounts rendered for `servings` portions.
 * Without a portion count on the version the amounts are only
 * formatted (factor 1).
 */
export function scaled_ingredients(version, servings)
{
	const f = can_scale(version) && servings > 0 ?
		  servings / version.servings : 1;
	return (version.ingredients || []).map(i => Object.assign({}, i, {
		amount: scale_amount(i.amount, f) }));
}

/* ------------------------------------------------------------------ */
/* Timers in step text                                                 */
/* ------------------------------------------------------------------ */

const NUM = "(\\d+(?:[.,]\\d+)?)";
const RANGE = "(?:\\s*(?:-|–|bis)\\s*" + NUM + ")?";
const UNIT = "(stunden?|std\\.?|h|minuten?|min\\.?|sekunden?|sek\\.?|s)";
const DURATION_RE = new RegExp("(?<![\\d.,])" + NUM + RANGE + "\\s*" +
			       UNIT + "(?![a-zäöü])", "gi");

const UNITS = [
	[/^(stunde|std|h)/, "Std", 3600],
	[/^(minute|min)/, "Min", 60],
	[/^(sekunde|sek|s)/, "Sek", 1],
];

function unit_info(u)
{
	const k = u.toLowerCase();
	for (const [re, label, secs] of UNITS)
		if (re.test(k))
			return { label: label, secs: secs };
	return null;
}

function find_durations(text)
{
	const out = [];
	for (const m of String(text || "").matchAll(DURATION_RE)) {
		const u = unit_info(m[3]);
		const n = parseFloat(m[1].replace(",", "."));
		if (!u || !(n > 0))
			continue;
		const num = m[2] ? m[1] + "–" + m[2] : m[1];
		out.push({ label: num + " " + u.label,
			   seconds: Math.round(n * u.secs),
			   unit: u.label,
			   start: m.index, end: m.index + m[0].length });
	}
	return out;
}

/* "1 h 30 min" is one timer, not two. */
function merge_hours_minutes(text, items)
{
	const out = [];
	for (let i = 0; i < items.length; i++) {
		const a = items[i];
		const b = items[i + 1];
		const gap = b ? text.slice(a.end, b.start) : "";
		if (b && a.unit === "Std" && b.unit === "Min" &&
		    /^\s*(und\s*)?$/.test(gap)) {
			out.push({ label: a.label + " " + b.label,
				   seconds: a.seconds + b.seconds });
			i++;
		} else {
			out.push({ label: a.label, seconds: a.seconds });
		}
	}
	return out;
}

/*
 * Durations in a step text, at most three, same duration once.
 * A range counts with its lower bound.
 */
export function parse_timers(text)
{
	const seen = new Set();
	const out = [];
	for (const t of merge_hours_minutes(text, find_durations(text))) {
		if (seen.has(t.seconds))
			continue;
		seen.add(t.seconds);
		out.push(t);
		if (out.length >= MAX_TIMERS_PER_STEP)
			break;
	}
	return out;
}

export function format_countdown(seconds)
{
	const s = Math.max(0, seconds);
	const pad = (n) => String(n).padStart(2, "0");
	const h = Math.floor(s / 3600);
	const m = Math.floor((s % 3600) / 60);
	const sec = s % 60;
	return (h ? h + ":" : "") + pad(m) + ":" + pad(sec);
}

/* ------------------------------------------------------------------ */
/* Servings state (sessionStorage per recipe id)                       */
/* ------------------------------------------------------------------ */

function clamp_servings(n)
{
	return Math.min(Math.max(n, SERVINGS_MIN), SERVINGS_MAX);
}

export function load_servings(id, fallback)
{
	let n = NaN;
	try {
		n = parseInt(sessionStorage.getItem(STORE_PREFIX + id), 10);
	} catch (e) {
		/* storage blocked */
	}
	return Number.isInteger(n) && n > 0 ? clamp_servings(n) : fallback;
}

export function save_servings(id, n)
{
	try {
		sessionStorage.setItem(STORE_PREFIX + id, String(n));
	} catch (e) {
		/* keep going without it */
	}
}

/* ------------------------------------------------------------------ */
/* Stepper                                                             */
/* ------------------------------------------------------------------ */

/*
 * «−  4 Portionen  +». on_change(n) runs after every tap; the value
 * is stored per recipe so detail and cooking mode agree.
 */
export function servings_stepper(h, id, version, on_change)
{
	let n = load_servings(id, version.servings);
	const value = h("span", { class: "stepper-value" },
			format_servings(n));
	const set = (next) => {
		n = clamp_servings(next);
		value.textContent = format_servings(n);
		save_servings(id, n);
		on_change(n);
	};
	return h("div", { class: "stepper", role: "group",
			  "aria-label": "Portionen" },
		h("button", { type: "button", "aria-label": "Weniger",
			      onclick: () => set(n - 1) }, "−"),
		value,
		h("button", { type: "button", "aria-label": "Mehr",
			      onclick: () => set(n + 1) }, "+"));
}
