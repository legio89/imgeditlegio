/* Service worker mínimo de VEXTAR (PWA shell).
 * Cachea el shell de la aplicación para uso offline básico.
 * Las llamadas a la API nunca se cachean: siempre van al backend local.
 */
const CACHE_NAME = "vextar-shell-v1";
const SHELL_FILES = ["/", "/index.html", "/manifest.webmanifest", "/icon.svg"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_FILES)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)),
        ),
      ),
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  // La API y las imágenes del backend siempre van a red.
  if (url.pathname.startsWith("/api") || url.pathname.includes("/assets/")) {
    return;
  }
  if (event.request.method !== "GET") {
    return;
  }
  event.respondWith(
    caches.match(event.request).then(
      (cached) =>
        cached ||
        fetch(event.request).then((response) => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
          return response;
        }),
    ),
  );
});
