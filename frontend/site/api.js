/*
 * Thin fetch wrapper for the recipe API (see docs/PLAN.md).
 *
 * Every call sends the session cookie. Errors are thrown as Error
 * with the server's "detail" as message. A 401 on any call except
 * login fires UNAUTHORIZED_EVENT on window so the app can show the
 * login screen.
 */

const API_BASE = "/api";
const LOGIN_PATH = "/auth/login";

export const UNAUTHORIZED_EVENT = "api:unauthorized";

export async function api(method, path, body)
{
	const opts = {
		method: method,
		credentials: "same-origin",
		headers: { "Accept": "application/json" },
	};
	if (body !== undefined) {
		opts.headers["Content-Type"] = "application/json";
		opts.body = JSON.stringify(body);
	}
	let res;
	try {
		res = await fetch(API_BASE + path, opts);
	} catch (e) {
		throw new Error("Keine Verbindung zum Server");
	}
	if (res.status === 401 && path !== LOGIN_PATH)
		window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT));
	const data = await read_body(res);
	if (!res.ok)
		throw new Error(error_detail(data, res.status));
	return data;
}

async function read_body(res)
{
	if (res.status === 204)
		return null;
	const text = await res.text();
	if (!text)
		return null;
	try {
		return JSON.parse(text);
	} catch (e) {
		return { detail: text };
	}
}

function error_detail(data, status)
{
	const d = data && data.detail;
	if (typeof d === "string")
		return d;
	if (Array.isArray(d))
		return d.map(e => e.msg || JSON.stringify(e)).join("; ");
	if (status === 401)
		return "Nicht angemeldet";
	if (status === 404)
		return "Nicht gefunden";
	return "Fehler " + status;
}

/*
 * Build a query string, skipping empty values.
 */
function query(params)
{
	const q = new URLSearchParams();
	for (const [k, v] of Object.entries(params || {})) {
		if (v === undefined || v === null || v === "" || v === false)
			continue;
		q.set(k, String(v));
	}
	const s = q.toString();
	return s ? "?" + s : "";
}

export function login(username, password)
{
	return api("POST", LOGIN_PATH, { username, password });
}

export function logout()
{
	return api("POST", "/auth/logout");
}

export function me()
{
	return api("GET", "/auth/me");
}

export function list_recipes(params)
{
	return api("GET", "/recipes" + query(params));
}

export function get_recipe(id)
{
	return api("GET", "/recipes/" + encodeURIComponent(id));
}

export function create_recipe(input)
{
	return api("POST", "/recipes", input);
}

export function update_recipe(id, input)
{
	return api("PUT", "/recipes/" + encodeURIComponent(id), input);
}

export function delete_recipe(id)
{
	return api("DELETE", "/recipes/" + encodeURIComponent(id));
}

export function list_categories()
{
	return api("GET", "/categories");
}

export function create_category(name)
{
	return api("POST", "/categories", { name });
}

export function list_tags()
{
	return api("GET", "/tags");
}
