/*
 * Minimal service worker: precache the app shell, serve it cache-first
 * and never touch /api, /media or /share/ photos (network only).
 *
 * Bump CACHE_VERSION whenever a shell file changes.
 */

const CACHE_VERSION = "v5";
const CACHE_NAME = "rezepte-shell-" + CACHE_VERSION;

const SHELL = [
	"/",
	"/index.html",
	"/app.js",
	"/api.js",
	"/cook.js",
	"/form.js",
	"/import.js",
	"/scale.js",
	"/share.js",
	"/shopping.js",
	"/style.css",
	"/manifest.webmanifest",
	"/icons/icon-192.png",
	"/icons/icon-512.png",
	"/icons/icon-512-maskable.png",
	"/icons/apple-touch-icon.png",
];

/* "/share/" are public photos; the bare share target "/share" is the shell. */
const NETWORK_ONLY = ["/api/", "/media/", "/share/"];

self.addEventListener("install", (ev) => {
	ev.waitUntil(
		caches.open(CACHE_NAME)
			.then(c => c.addAll(SHELL))
			.then(() => self.skipWaiting())
	);
});

self.addEventListener("activate", (ev) => {
	ev.waitUntil(
		caches.keys()
			.then(keys => Promise.all(
				keys.filter(k => k !== CACHE_NAME)
					.map(k => caches.delete(k))
			))
			.then(() => self.clients.claim())
	);
});

function is_network_only(url)
{
	return NETWORK_ONLY.some(p => url.pathname.startsWith(p));
}

function shell_path(url)
{
	/* Any navigation inside the app resolves to the shell. */
	return url.pathname === "/" || url.pathname.endsWith(".html") ||
	       url.pathname === "/share"
		? "/index.html" : url.pathname;
}

self.addEventListener("fetch", (ev) => {
	const req = ev.request;
	if (req.method !== "GET")
		return;
	const url = new URL(req.url);
	if (url.origin !== self.location.origin || is_network_only(url))
		return;
	ev.respondWith(cache_first(req, shell_path(url)));
});

async function cache_first(req, key)
{
	const cache = await caches.open(CACHE_NAME);
	const hit = await cache.match(key);
	if (hit) {
		refresh(cache, req, key);
		return hit;
	}
	const res = await fetch(req);
	if (res.ok && SHELL.includes(key))
		cache.put(key, res.clone());
	return res;
}

/*
 * Stale-while-revalidate: update the cached shell in the background so
 * a new deployment is picked up on the next load.
 */
function refresh(cache, req, key)
{
	fetch(req).then(res => {
		if (res.ok)
			cache.put(key, res.clone());
	}).catch(() => {});
}
