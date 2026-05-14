// AI Daily — AA API Proxy Worker
// Proxies artificialanalysis.ai API calls, injects x-api-key server-side.
// Frontend never sees the API key.

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const origin = request.headers.get("Origin") || "";

    // CORS preflight
    if (request.method === "OPTIONS") {
      return corsResponse(new Response(null, { status: 204 }), env.ALLOWED_ORIGIN, origin);
    }

    // Only proxy /v2/* paths
    if (!url.pathname.startsWith("/v2/")) {
      return new Response("Not Found", { status: 404 });
    }

    // Build upstream request
    const upstream = `${env.AA_API_BASE}${url.pathname}${url.search}`;
    const headers = new Headers(request.headers);
    headers.set("x-api-key", env.AA_API_KEY);
    // Remove host header that points to worker
    headers.delete("Host");

    try {
      const resp = await fetch(upstream, {
        method: request.method,
        headers,
      });

      // Clone response and add CORS
      const body = await resp.arrayBuffer();
      return corsResponse(
        new Response(body, {
          status: resp.status,
          statusText: resp.statusText,
          headers: resp.headers,
        }),
        env.ALLOWED_ORIGIN,
        origin
      );
    } catch (e) {
      return corsResponse(
        new Response(JSON.stringify({ error: "Upstream unavailable" }), {
          status: 502,
          headers: { "Content-Type": "application/json" },
        }),
        env.ALLOWED_ORIGIN,
        origin
      );
    }
  },
};

function corsResponse(resp, allowedOrigin, requestOrigin) {
  const headers = new Headers(resp.headers);
  // Allow configured origin + localhost dev
  const allowed = [allowedOrigin, "http://localhost:8080", "http://127.0.0.1:8080"];
  if (allowed.includes(requestOrigin)) {
    headers.set("Access-Control-Allow-Origin", requestOrigin);
  }
  headers.set("Access-Control-Allow-Methods", "GET, OPTIONS");
  headers.set("Access-Control-Allow-Headers", "Content-Type");
  headers.set("Access-Control-Max-Age", "86400");
  // Don't cache trend data too long (data updates daily)
  headers.set("Cache-Control", "public, max-age=3600");
  return new Response(resp.body, {
    status: resp.status,
    statusText: resp.statusText,
    headers,
  });
}
