const CACHE = "pwabuilder-offline";
const CACHE_HTML = "pwabuilder-html";

importScripts('https://storage.googleapis.com/workbox-cdn/releases/5.1.2/workbox-sw.js');

self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") {
    self.skipWaiting();
  }
});

// HTML 导航请求：用 StaleWhileRevalidate，立即返回缓存版本（保证存档与游戏版本一致），
// 同时后台同步更新。避免后台恢复时 NetworkFirst 拉取新版游戏，导致旧存档因 SugarCube
// 版本校验失败而被判定为空。首次访问（无缓存）仍走网络获取最新版本。
workbox.routing.registerRoute(
  ({ request }) => request.mode === "navigate",
  new workbox.strategies.StaleWhileRevalidate({ cacheName: CACHE_HTML })
);

// 其他静态资源：NetworkFirst，优先获取更新，离线时回退缓存。
workbox.routing.registerRoute(
  new RegExp("/*"),
  new workbox.strategies.NetworkFirst({ cacheName: CACHE })
);