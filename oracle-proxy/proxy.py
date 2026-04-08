"""
Figurya Residential Proxy — runs on Oracle Cloud Free Tier VM.
Proxies requests for stores that block Cloudflare Worker IPs.

Usage:
  GET http://<vm-ip>:9090/?url=<encoded_target_url>
  Header: X-Proxy-Key: <shared_secret>
"""

import os
import sys
from urllib.parse import unquote

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse

PROXY_KEY = os.environ.get("PROXY_KEY", "")

app = FastAPI()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


@app.get("/health")
async def health():
    return PlainTextResponse("ok")


@app.get("/")
async def proxy(request: Request, url: str = ""):
    # Auth check
    key = request.headers.get("X-Proxy-Key", "")
    if not PROXY_KEY or key != PROXY_KEY:
        return PlainTextResponse("Unauthorized", status_code=401)

    if not url or not url.startswith(("http://", "https://")):
        return PlainTextResponse("Missing or invalid ?url= parameter", status_code=400)

    try:
        async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
            resp = await client.get(url, headers=HEADERS)

        return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers={
                "Content-Type": resp.headers.get("content-type", "text/html"),
                "X-Proxy-Status": str(resp.status_code),
            },
        )
    except Exception as e:
        return PlainTextResponse(f"Proxy error: {e}", status_code=502)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "9090"))
    uvicorn.run(app, host="0.0.0.0", port=port)
