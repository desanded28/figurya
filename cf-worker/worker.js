// Figurya Scraping Proxy — Cloudflare Worker
//
// Proxies HTTP requests through Cloudflare's edge network so that
// store websites see requests coming from CF edge IPs instead of
// our Railway/Render datacenter IP. This bypasses IP-based blocks
// on Amazon, Hobby Genki, Otaku Republic, etc.
//
// Usage:
//   GET https://<worker-url>/?url=<encoded_target_url>
//   Header: X-Proxy-Key: <shared_secret>

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // Shared-secret auth so randoms can't abuse the worker
    const key = request.headers.get("X-Proxy-Key");
    if (!env.PROXY_KEY || key !== env.PROXY_KEY) {
      return new Response("Unauthorized", { status: 401 });
    }

    const target = url.searchParams.get("url");
    if (!target) {
      return new Response("Missing ?url= parameter", { status: 400 });
    }

    // Basic SSRF guard: only allow http(s) URLs
    let targetUrl;
    try {
      targetUrl = new URL(target);
    } catch {
      return new Response("Invalid URL", { status: 400 });
    }
    if (!["http:", "https:"].includes(targetUrl.protocol)) {
      return new Response("Only http/https allowed", { status: 400 });
    }

    // Pass through client-specified headers (minus our auth header)
    // plus a realistic browser UA if none provided.
    const headers = new Headers();
    for (const [k, v] of request.headers) {
      const lk = k.toLowerCase();
      if (["x-proxy-key", "host", "cf-connecting-ip", "cf-ray", "cf-visitor",
           "x-forwarded-for", "x-forwarded-proto", "x-real-ip"].includes(lk)) continue;
      headers.set(k, v);
    }
    if (!headers.has("user-agent")) {
      headers.set("user-agent",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " +
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36");
    }
    if (!headers.has("accept")) {
      headers.set("accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8");
    }
    if (!headers.has("accept-language")) {
      headers.set("accept-language", "en-US,en;q=0.9");
    }

    // Fetch through Cloudflare's network
    try {
      const upstream = await fetch(targetUrl.toString(), {
        method: request.method,
        headers,
        redirect: "follow",
        body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
      });

      // Return the response body + content-type, with permissive CORS
      const respHeaders = new Headers();
      respHeaders.set("content-type", upstream.headers.get("content-type") || "text/html");
      respHeaders.set("access-control-allow-origin", "*");
      respHeaders.set("x-proxy-status", String(upstream.status));

      return new Response(upstream.body, {
        status: upstream.status,
        headers: respHeaders,
      });
    } catch (err) {
      return new Response(`Proxy error: ${err.message}`, { status: 502 });
    }
  },
};
