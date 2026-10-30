/*
 * Thin fetch wrapper for the recipe API (see docs/PLAN.md).
 *
 * Every call sends the session cookie. Errors are thrown as Error
 * with the server's "detail" as message. A 401 on any call except
 * the public ones fires UNAUTHORIZED_EVENT on window so the app can
 * show the login screen. A FormData body is sent as multipart without a JSON
 * content type.
 */

const API_BASE = "/api";
const LOGIN_PATH = "/auth/login";
/* Paths that work without a session: a 401 there is not a logout. */
const SETUP_PATH = "/auth/setup";
const PUBLIC_PREFIXES = [LOGIN_PATH, SETUP_PATH, "/share/"];

export const UNAUTHORIZED_EVENT = "api:unauthorized";

export async function api(method, path, body)
{
	const opts = {
		method: method,
		credentials: "same-origin",
		headers: { "Accept": "application/json" },
	};
	if (body instanceof FormData) {
		opts.body = body;
	} else if (body !== undefined) {
		opts.headers["Content-Type"] = "application/json";
		opts.body = JSON.stringify(body);
	}
	let res;
	try {
		res = await fetch(API_BASE + path, opts);
	} catch (e) {
		throw new Error("Keine Verbindung zum Server");
	}
	if (res.status === 401 && !is_public(path))
		window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT));
	const data = await read_body(res);
	if (!res.ok)
		throw new Error(error_detail(data, res.status));
	return data;
}

function is_public(path)
{
	return PUBLIC_PREFIXES.some(p => path.startsWith(p));
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

export function setup_state()
{
	return api("GET", SETUP_PATH);
}

export function setup(username, password)
{
	return api("POST", SETUP_PATH, { username, password });
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

function recipe_path(id, sub)
{
	return "/recipes/" + encodeURIComponent(id) + sub;
}

export function add_note(id, text)
{
	return api("POST", recipe_path(id, "/notes"), { text });
}

export function delete_note(id, nid)
{
	return api("DELETE",
		   recipe_path(id, "/notes/" + encodeURIComponent(nid)));
}

/* entry: {cooked_on: "yyyy-mm-dd", rating: 1-5 | null, comment} */
export function add_cooklog(id, entry)
{
	return api("POST", recipe_path(id, "/cooklog"), entry);
}

export function delete_cooklog(id, cid)
{
	return api("DELETE",
		   recipe_path(id, "/cooklog/" + encodeURIComponent(cid)));
}

export function set_favorite(id, favorite)
{
	return api("PUT", recipe_path(id, "/favorite"),
		   { favorite: !!favorite });
}

export function upload_photo(id, file, is_own_result)
{
	const fd = new FormData();
	fd.append("file", file, file.name || "foto.jpg");
	fd.append("is_own_result", is_own_result ? "true" : "false");
	return api("POST", recipe_path(id, "/photos"), fd);
}

export function delete_photo(id, pid)
{
	return api("DELETE",
		   recipe_path(id, "/photos/" + encodeURIComponent(pid)));
}

export function export_url()
{
	return API_BASE + "/export";
}

/* -> ImportPreview; saves nothing */
export function import_fetch(url)
{
	return api("POST", "/import/fetch", { url });
}

/* lines: [str] -> [{amount, unit, name, note, raw}] */
export function parse_ingredients(lines)
{
	return api("POST", "/import/ingredients", { lines });
}

export function add_photo_from_url(id, url)
{
	return api("POST", recipe_path(id, "/photos/url"), { url });
}

/* -> ImportPreview with method "ocr"; saves nothing */
export function import_photo(file)
{
	const fd = new FormData();
	fd.append("file", file, file.name || "seite.jpg");
	return api("POST", "/import/photo", fd);
}

/* ---- shopping list ---- */

function shopping_path(id, sub)
{
	return "/shopping/" + encodeURIComponent(id) + (sub || "");
}

export function list_shopping()
{
	return api("GET", "/shopping");
}

/* item: {name, unit, amount, note} */
export function add_shopping(item)
{
	return api("POST", "/shopping", item);
}

/* factor scales the amounts: 2 of 4 portions is 0.5 */
export function add_shopping_from_recipe(id, factor)
{
	return api("POST", "/shopping/from-recipe/" + encodeURIComponent(id),
		   { factor: factor });
}

export function update_shopping(id, item)
{
	return api("PUT", shopping_path(id), item);
}

export function set_shopping_checked(id, checked)
{
	return api("PUT", shopping_path(id, "/checked"),
		   { checked: !!checked });
}

export function remove_shopping(id)
{
	return api("DELETE", shopping_path(id));
}

export function clear_checked_shopping()
{
	return api("DELETE", "/shopping/checked");
}

/* ---- pantry ---- */

export function list_pantry()
{
	return api("GET", "/pantry");
}

export function add_pantry(name)
{
	return api("POST", "/pantry", { name });
}

export function remove_pantry(id)
{
	return api("DELETE", "/pantry/" + encodeURIComponent(id));
}

/* ---- sharing ---- */

export function get_share(id)
{
	return api("GET", recipe_path(id, "/share"));
}

export function enable_share(id)
{
	return api("POST", recipe_path(id, "/share"));
}

export function disable_share(id)
{
	return api("DELETE", recipe_path(id, "/share"));
}

/* Public: no session needed, a 401 does not log out. */
export function get_shared(token)
{
	return api("GET", "/share/" + encodeURIComponent(token));
}

/* ---- Microsoft To Do ---- */

export function todo_status()
{
	return api("GET", "/todo/status");
}

export function todo_push()
{
	return api("POST", "/todo/push");
}
