import asyncio
import hashlib
import logging
import os
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

SITE_URL = "https://figuryaa.onrender.com"

from weebshelf.query import parse_query, build_search_terms
from weebshelf.fetchers.hobbysearch import HobbySearchFetcher
from weebshelf.fetchers.hlj import HLJFetcher
from weebshelf.fetchers.solaris import SolarisFetcher
from weebshelf.fetchers.tom import TOMFetcher
from weebshelf.fetchers.cdjapan import CDJapanFetcher
from weebshelf.fetchers.hobbygenki import HobbyGenkiFetcher
from weebshelf.fetchers.ninnin import NinNinFetcher
from weebshelf.fetchers.amazon import AmazonFetcher
from weebshelf.fetchers.surugaya import SurugayaFetcher
from weebshelf.fetchers.plaza import PlazaJapanFetcher
from weebshelf.fetchers.navito import NavitoFetcher
from weebshelf.fetchers.otakurepublic import OtakuRepublicFetcher
from weebshelf.fetchers.goodsmile import GoodSmileFetcher
from weebshelf.fetchers.kotobukiya import KotobukiyaFetcher
from weebshelf.fetchers.animate import AnimateFetcher
from weebshelf.ranker import rank_results
from weebshelf.reviews import summarize_reviews
from weebshelf.database import get_cached_results, queue_search_term, store_search_results, db_conn, get_db_stats, init_db
from weebshelf.crawler import crawler_loop, run_initial_crawl
from weebshelf.models import Figurine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("figurya")

VALID_SORTS = {"relevance", "price_low", "price_high", "rating"}
MAX_QUERY_LENGTH = 200
RESULTS_PER_PAGE = 50
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX = 30     # max requests per window per IP

FETCHERS = [
    HobbySearchFetcher(),
    HLJFetcher(),
    SolarisFetcher(),
    TOMFetcher(),
    CDJapanFetcher(),
    HobbyGenkiFetcher(),
    NinNinFetcher(),
    AmazonFetcher(),
    SurugayaFetcher(),
    PlazaJapanFetcher(),
    NavitoFetcher(),
    OtakuRepublicFetcher(),
    GoodSmileFetcher(),
    KotobukiyaFetcher(),
    AnimateFetcher(),
]

crawler_task = None

# Admin dashboard password — set via FIGURYA_ADMIN_PASS env var, default for local dev
ADMIN_PASSWORD = os.environ.get("FIGURYA_ADMIN_PASS", "figurya-admin-2024")

# Image proxy cache directory
IMG_CACHE_DIR = Path(__file__).parent.parent / "img_cache"
IMG_CACHE_DIR.mkdir(exist_ok=True)

rate_limit_store: dict[str, list[float]] = defaultdict(list)


_last_purge = 0.0

def is_rate_limited(ip: str) -> bool:
    global _last_purge
    now = time.time()

    # purge stale IPs every hour so the dict doesn't grow forever
    if now - _last_purge > 3600:
        stale = [k for k, v in rate_limit_store.items() if not v or now - v[-1] > RATE_LIMIT_WINDOW]
        for k in stale:
            del rate_limit_store[k]
        _last_purge = now

    rate_limit_store[ip] = [t for t in rate_limit_store[ip] if now - t < RATE_LIMIT_WINDOW]
    if len(rate_limit_store[ip]) >= RATE_LIMIT_MAX:
        return True
    rate_limit_store[ip].append(now)
    return False


async def _background_startup():
    """Run initial crawl + start crawler loop, all in background."""
    await run_initial_crawl(FETCHERS)
    await crawler_loop(FETCHERS, interval_hours=12)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global crawler_task
    init_db()
    crawler_task = asyncio.create_task(_background_startup())
    yield
    # Shutdown gracefully
    if crawler_task:
        crawler_task.cancel()
        try:
            await crawler_task
        except asyncio.CancelledError:
            logger.info("Crawler task cancelled on shutdown")


app = FastAPI(title="Figurya", lifespan=lifespan)

BASE_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt():
    return """User-agent: *
Allow: /
Disallow: /?q=*&sort=*&page=2
Disallow: /?q=*&sort=*&page=3
Disallow: /?q=*&sort=*&page=4
Disallow: /?q=*&sort=*&page=5

Sitemap: {}/sitemap.xml

# Figurya — Anime Figurine Search Engine
# https://github.com/sanderfloria/weebshelf
""".format(SITE_URL)


@app.get("/sitemap.xml", response_class=PlainTextResponse)
async def sitemap_xml():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>{url}/</loc>
        <changefreq>daily</changefreq>
        <priority>1.0</priority>
    </url>
    <url>
        <loc>{url}/donate</loc>
        <changefreq>monthly</changefreq>
        <priority>0.5</priority>
    </url>
</urlset>""".format(url=SITE_URL)
    return PlainTextResponse(content=xml, media_type="application/xml")


@app.get("/donate")
async def donate(request: Request):
    stats = get_db_stats()
    return templates.TemplateResponse("donate.html", {
        "request": request,
        "stats": stats,
        "meta_description": "Support Figurya with a donation. Help keep the anime figurine search engine free, fast, and online for all collectors.",
        "og_title": "Support Figurya — Help Keep It Free",
        "canonical_url": f"{SITE_URL}/donate",
    })


@app.get("/")
async def home(request: Request, q: str = "", sort: str = "relevance", page: int = 1):
    # ── Rate limiting ──
    client_ip = request.client.host if request.client else "unknown"
    if is_rate_limited(client_ip):
        logger.warning(f"Rate limited IP: {client_ip}")
        stats = get_db_stats()
        return templates.TemplateResponse("429.html", {
            "request": request,
            "stats": stats,
            "meta_description": "Too many requests. Please wait a moment before searching again.",
            "og_title": "Slow Down | Figurya",
            "canonical_url": SITE_URL,
        }, status_code=429)

    # ── Input validation ──
    q = q[:MAX_QUERY_LENGTH]  # Silently truncate overly long queries
    if sort not in VALID_SORTS:
        sort = "relevance"
    if page < 1:
        page = 1

    search_start = time.time()

    if not q.strip():
        stats = get_db_stats()
        return templates.TemplateResponse("index.html", {
            "request": request,
            "query": "",
            "results": [],
            "parsed": None,
            "sort": sort,
            "stats": stats,
            "from_cache": True,
            "has_more": False,
            "page": 1,
            "total_results": 0,
            "canonical_url": SITE_URL,
        })

    parsed = parse_query(q)
    search_term = build_search_terms(parsed)

    # Step 1: Check the database for cached results
    cached = get_cached_results(search_term)

    from_cache = bool(cached)
    if cached:
        figurines = [Figurine(**f) for f in cached]
    else:
        # Step 2: Not in DB — do a live fetch (just this once), store it, and queue for future crawls
        logger.info(f"Live fetch for query: {q!r} (term: {search_term!r})")
        tasks = [fetcher.search(search_term) for fetcher in FETCHERS]
        results_lists = await asyncio.gather(*tasks, return_exceptions=True)

        figurines = []
        for result in results_lists:
            if isinstance(result, list):
                figurines.extend(result)
            elif isinstance(result, Exception):
                logger.error(f"Fetcher error: {result}")

        # Store in the proper database
        if figurines:
            with db_conn() as conn:
                store_search_results(conn, search_term, [f.model_dump() for f in figurines])
        else:
            # Queue the term so the crawler picks it up next cycle
            queue_search_term(search_term)

    # Rank results
    results = rank_results(figurines, parsed)

    # Generate review summaries
    for r in results:
        if r.figurine.reviews:
            r.review_summary = summarize_reviews(r.figurine.reviews)

    # Sort
    if sort == "price_low":
        results.sort(key=lambda r: r.figurine.price_usd or 99999)
    elif sort == "price_high":
        results.sort(key=lambda r: -(r.figurine.price_usd or 0))
    elif sort == "rating":
        results.sort(key=lambda r: -(r.figurine.rating or 0))
    # default: relevance (already sorted by final_score)

    # Pagination
    total_results = len(results)
    start = (page - 1) * RESULTS_PER_PAGE
    end = start + RESULTS_PER_PAGE
    paginated = results[start:end]
    has_more = end < total_results

    stats = get_db_stats()

    search_time = time.time() - search_start
    logger.info(f'Search for "{q}" took {search_time:.2f}s ({total_results} results)')

    return templates.TemplateResponse("index.html", {
        "request": request,
        "query": q,
        "results": paginated,
        "parsed": parsed,
        "sort": sort,
        "stats": stats,
        "from_cache": from_cache,
        "has_more": has_more,
        "page": page,
        "total_results": total_results,
        "search_time": round(search_time, 2),
        "meta_description": f"Found {total_results} anime figurines for \"{q}\" across 15 stores. Compare prices and availability from AmiAmi, Solaris Japan, HobbySearch, and more.",
        "og_title": f"{q} — Figurine Search Results | Figurya",
        "canonical_url": f"{SITE_URL}/?q={q}",
    })


# ── Image Proxy ──────────────────────────────────────────────

@app.get("/img")
async def image_proxy(url: str = ""):
    """Proxy and cache external product images to avoid hotlink blocks."""
    if not url or not url.startswith(("http://", "https://")):
        return Response(status_code=400)

    # Use URL hash as cache key
    url_hash = hashlib.md5(url.encode()).hexdigest()
    cache_path = IMG_CACHE_DIR / url_hash

    # Serve from disk cache if fresh (7 days)
    if cache_path.exists():
        age = time.time() - cache_path.stat().st_mtime
        if age < 604800:
            data = cache_path.read_bytes()
            # Guess content type from first bytes
            ct = "image/jpeg"
            if data[:4] == b"\x89PNG":
                ct = "image/png"
            elif data[:4] == b"GIF8":
                ct = "image/gif"
            elif data[:4] == b"RIFF":
                ct = "image/webp"
            return Response(content=data, media_type=ct, headers={
                "Cache-Control": "public, max-age=604800",
            })

    # Fetch from source
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "image/*,*/*;q=0.8",
            })
            if resp.status_code != 200:
                return Response(status_code=502)

            content_type = resp.headers.get("content-type", "")
            if "image" not in content_type:
                return Response(status_code=502)

            data = resp.content
            # Don't cache files larger than 5MB
            if len(data) < 5_000_000:
                cache_path.write_bytes(data)

            return Response(content=data, media_type=content_type, headers={
                "Cache-Control": "public, max-age=604800",
            })
    except Exception:
        return Response(status_code=502)


# ── Search Autocomplete ─────────────────────────────────────

@app.get("/api/autocomplete")
async def autocomplete(q: str = ""):
    """Return matching search terms from the database for autocomplete."""
    q = q.strip()[:100]
    if len(q) < 2:
        return JSONResponse([])

    with db_conn() as conn:
        rows = conn.execute("""
            SELECT term, popularity FROM search_terms
            WHERE term LIKE ?
            ORDER BY popularity DESC
            LIMIT 8
        """, (f"%{q}%",)).fetchall()

    suggestions = [{"term": r["term"], "popularity": r["popularity"]} for r in rows]
    return JSONResponse(suggestions)


# ── Admin Dashboard ──────────────────────────────────────────

def _check_admin(request: Request) -> bool:
    """Check if the admin session cookie is valid."""
    token = request.cookies.get("figurya_admin")
    expected = hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest()[:32]
    return token == expected


@app.get("/admin/login")
async def admin_login_page(request: Request):
    if _check_admin(request):
        return RedirectResponse("/admin", status_code=302)
    return templates.TemplateResponse("admin_login.html", {"request": request})


@app.post("/admin/login")
async def admin_login_submit(request: Request):
    form = await request.form()
    password = form.get("password", "")
    if password == ADMIN_PASSWORD:
        token = hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest()[:32]
        response = RedirectResponse("/admin", status_code=302)
        response.set_cookie("figurya_admin", token, httponly=True, max_age=86400 * 7)
        return response
    return templates.TemplateResponse("admin_login.html", {
        "request": request, "error": "Wrong password",
    })


@app.get("/admin/debug")
async def admin_debug():
    """Temporary debug endpoint to diagnose admin 500 on Render."""
    import traceback
    errors = []
    info = {}

    try:
        stats = get_db_stats()
        info["stats"] = stats
    except Exception as e:
        errors.append(f"get_db_stats: {traceback.format_exc()}")

    try:
        with db_conn() as conn:
            rows = conn.execute("SELECT COUNT(*) as c FROM figurines").fetchone()
            info["figurines_count"] = rows["c"]
    except Exception as e:
        errors.append(f"figurines query: {traceback.format_exc()}")

    try:
        with db_conn() as conn:
            rows = conn.execute("SELECT COUNT(*) as c FROM search_terms").fetchone()
            info["search_terms_count"] = rows["c"]
    except Exception as e:
        errors.append(f"search_terms query: {traceback.format_exc()}")

    try:
        info["img_cache_exists"] = IMG_CACHE_DIR.exists()
        if IMG_CACHE_DIR.exists():
            files = list(IMG_CACHE_DIR.iterdir())
            info["img_cache_files"] = len(files)
    except Exception as e:
        errors.append(f"img_cache: {traceback.format_exc()}")

    try:
        info["fetcher_count"] = len(FETCHERS)
        info["template_dir"] = str(BASE_DIR / "templates")
        info["template_exists"] = (BASE_DIR / "templates" / "admin.html").exists()
    except Exception as e:
        errors.append(f"misc: {traceback.format_exc()}")

    # Try actually rendering the template
    try:
        from starlette.testclient import TestClient
        stats = get_db_stats()
        html = templates.get_template("admin.html").render(
            request=None,
            stats=stats,
            stores=[],
            recent_searches=[],
            cache_fresh=0,
            cache_stale=0,
            img_cache_count=0,
            img_cache_size_mb=0,
            fetcher_count=len(FETCHERS),
        )
        info["template_renders"] = True
    except Exception as e:
        errors.append(f"template render: {traceback.format_exc()}")
        info["template_renders"] = False

    return JSONResponse({"info": info, "errors": errors})


@app.get("/admin")
async def admin_dashboard(request: Request):
    if not _check_admin(request):
        return RedirectResponse("/admin/login", status_code=302)

    try:
        stats = get_db_stats()

        stores_data = []
        searches_data = []
        cache_fresh = 0
        cache_stale = 0

        with db_conn() as conn:
            # Store health: last results per store
            try:
                store_health = conn.execute("""
                    SELECT store, COUNT(*) as total,
                           SUM(CASE WHEN price IS NOT NULL THEN 1 ELSE 0 END) as with_price,
                           SUM(CASE WHEN image_url != '' THEN 1 ELSE 0 END) as with_image,
                           MAX(last_updated) as last_seen
                    FROM figurines
                    GROUP BY store
                    ORDER BY total DESC
                """).fetchall()

                now = time.time()
                for row in store_health:
                    age_hours = (now - row["last_seen"]) / 3600 if row["last_seen"] else 999
                    status = "healthy" if age_hours < 48 else "stale" if age_hours < 168 else "dead"
                    stores_data.append({
                        "name": row["store"],
                        "total": row["total"],
                        "with_price": row["with_price"],
                        "with_image": row["with_image"],
                        "age_hours": round(age_hours, 1),
                        "status": status,
                    })
            except Exception as e:
                logger.error(f"Admin store health query failed: {e}")

            # Recent searches
            try:
                recent_searches = conn.execute("""
                    SELECT term, popularity, last_crawled
                    FROM search_terms
                    ORDER BY last_crawled DESC
                    LIMIT 20
                """).fetchall()

                now = time.time()
                for row in recent_searches:
                    age = (now - row["last_crawled"]) / 3600 if row["last_crawled"] else 0
                    searches_data.append({
                        "term": row["term"],
                        "popularity": row["popularity"],
                        "age_hours": round(age, 1),
                    })
            except Exception as e:
                logger.error(f"Admin recent searches query failed: {e}")

            # Cache stats
            try:
                cache_fresh = conn.execute("""
                    SELECT COUNT(*) as c FROM search_terms
                    WHERE (? - last_crawled) / 3600.0 <= 24
                """, (time.time(),)).fetchone()["c"]

                cache_stale = conn.execute("""
                    SELECT COUNT(*) as c FROM search_terms
                    WHERE (? - last_crawled) / 3600.0 > 24
                """, (time.time(),)).fetchone()["c"]
            except Exception as e:
                logger.error(f"Admin cache stats query failed: {e}")

        # Image cache stats
        img_cache_count = 0
        img_cache_size_mb = 0.0
        try:
            if IMG_CACHE_DIR.exists():
                files = [f for f in IMG_CACHE_DIR.iterdir() if f.is_file()]
                img_cache_count = len(files)
                img_cache_size_mb = sum(f.stat().st_size for f in files) / 1_000_000
        except Exception as e:
            logger.error(f"Admin image cache stats failed: {e}")

        # Render template explicitly so errors are caught by try/except
        # (TemplateResponse renders lazily, bypassing our error handling)
        import traceback as tb
        try:
            template = templates.get_template("admin.html")
            html = template.render(
                request=request,
                stats=stats,
                stores=stores_data,
                recent_searches=searches_data,
                cache_fresh=cache_fresh,
                cache_stale=cache_stale,
                img_cache_count=img_cache_count,
                img_cache_size_mb=round(img_cache_size_mb, 1),
                fetcher_count=len(FETCHERS),
            )
            return HTMLResponse(html)
        except Exception as e:
            logger.error(f"Admin template render error: {tb.format_exc()}")
            return HTMLResponse(f"<h1>Admin Template Error</h1><pre>{tb.format_exc()}</pre>", status_code=500)
    except Exception as e:
        import traceback as tb
        logger.error(f"Admin dashboard error: {tb.format_exc()}")
        return HTMLResponse(f"<h1>Admin Error</h1><pre>{tb.format_exc()}</pre>", status_code=500)


class StaticCacheMiddleware(BaseHTTPMiddleware):
    """Add Cache-Control headers for static assets."""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "public, max-age=86400, stale-while-revalidate=3600"
        return response


app.add_middleware(StaticCacheMiddleware)


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Catch ALL unhandled exceptions so we see the actual error."""
    import traceback
    logger.error(f"Unhandled exception on {request.url.path}: {traceback.format_exc()}")
    return HTMLResponse(
        content=f"<h1>Server Error</h1><pre>{traceback.format_exc()}</pre>",
        status_code=500,
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        stats = get_db_stats()
        return templates.TemplateResponse("404.html", {
            "request": request,
            "stats": stats,
            "meta_description": "Page not found. Search anime figurines across 15 stores on Figurya.",
            "og_title": "Page Not Found | Figurya",
            "canonical_url": SITE_URL,
        }, status_code=404)
    if exc.status_code == 500:
        logger.error(f"Internal server error: {exc.detail}")
        stats = get_db_stats()
        return templates.TemplateResponse("500.html", {
            "request": request,
            "stats": stats,
            "meta_description": "Something went wrong. Please try again.",
            "og_title": "Error | Figurya",
            "canonical_url": SITE_URL,
        }, status_code=500)
    return HTMLResponse(
        content=f"<h1>Error {exc.status_code}</h1><p>{exc.detail or 'Something went wrong.'}</p>",
        status_code=exc.status_code,
    )


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def catch_all(request: Request, path: str):
    stats = get_db_stats()
    return templates.TemplateResponse("404.html", {
        "request": request,
        "stats": stats,
        "meta_description": "Page not found. Search anime figurines across 15 stores on Figurya.",
        "og_title": "Page Not Found | Figurya",
        "canonical_url": SITE_URL,
    }, status_code=404)


def main():
    import uvicorn
    uvicorn.run("weebshelf.app:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()
