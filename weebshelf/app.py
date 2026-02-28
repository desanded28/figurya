import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
import asyncio

# ── SEO Constants ─────────────────────────────────────────────
SITE_URL = "https://figuryaa.onrender.com"
SITE_NAME = "Figurya"
DEFAULT_DESCRIPTION = "Search anime figurines across 8 stores at once. Compare prices, find deals, and discover figures by character, style, or vibe. Free and open-source."
DEFAULT_OG_TITLE = "Figurya — Anime Figurine Search Engine"

from weebshelf.query import parse_query, build_search_terms
from weebshelf.fetchers.mfc import HobbySearchFetcher
from weebshelf.fetchers.amiami import HLJFetcher
from weebshelf.fetchers.solaris import SolarisFetcher
from weebshelf.fetchers.tom import TOMFetcher
from weebshelf.fetchers.cdjapan import CDJapanFetcher
from weebshelf.fetchers.hobbygenki import HobbyGenkiFetcher
from weebshelf.fetchers.ninnin import NinNinFetcher
from weebshelf.fetchers.amazon import AmazonFetcher
from weebshelf.ranker import rank_results
from weebshelf.reviews import summarize_reviews
from weebshelf.database import get_cached_results, queue_search_term, store_search_results, db_conn, get_db_stats
from weebshelf.crawler import crawler_loop, run_initial_crawl
from weebshelf.models import Figurine

# ── Logging setup ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("figurya")

# ── Constants ──────────────────────────────────────────────────
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
]

crawler_task = None

# ── Simple in-memory rate limiter ──────────────────────────────
rate_limit_store: dict[str, list[float]] = defaultdict(list)


def is_rate_limited(ip: str) -> bool:
    """Check if an IP has exceeded the rate limit."""
    now = time.time()
    # Clean old entries
    rate_limit_store[ip] = [t for t in rate_limit_store[ip] if now - t < RATE_LIMIT_WINDOW]
    if len(rate_limit_store[ip]) >= RATE_LIMIT_MAX:
        return True
    rate_limit_store[ip].append(now)
    return False


# ── Lifespan ───────────────────────────────────────────────────
async def _background_startup():
    """Run initial crawl + start crawler loop, all in background."""
    await run_initial_crawl(FETCHERS)
    await crawler_loop(FETCHERS, interval_hours=12)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global crawler_task
    # Start crawling in background — don't block server startup
    crawler_task = asyncio.create_task(_background_startup())
    yield
    # Shutdown gracefully
    if crawler_task:
        crawler_task.cancel()
        try:
            await crawler_task
        except asyncio.CancelledError:
            logger.info("Crawler task cancelled on shutdown")


# ── App setup ──────────────────────────────────────────────────
app = FastAPI(title="Figurya", lifespan=lifespan)

BASE_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# ── SEO Routes ────────────────────────────────────────────────
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


# ── Routes ─────────────────────────────────────────────────────
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
        return HTMLResponse(
            content="<h1>Too many requests</h1><p>Please wait a moment before searching again.</p>",
            status_code=429,
        )

    # ── Input validation ──
    q = q[:MAX_QUERY_LENGTH]  # Silently truncate overly long queries
    if sort not in VALID_SORTS:
        sort = "relevance"
    if page < 1:
        page = 1

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
        "meta_description": f"Found {total_results} anime figurines for \"{q}\" across 8 stores. Compare prices and availability from AmiAmi, Solaris Japan, HobbySearch, and more.",
        "og_title": f"{q} — Figurine Search Results | Figurya",
        "canonical_url": f"{SITE_URL}/?q={q}",
    })


# ── Custom error handlers ─────────────────────────────────────
from starlette.exceptions import HTTPException as StarletteHTTPException


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        stats = get_db_stats()
        return templates.TemplateResponse("404.html", {
            "request": request,
            "stats": stats,
            "meta_description": "Page not found. Search anime figurines across 8 stores on Figurya.",
            "og_title": "Page Not Found | Figurya",
            "canonical_url": SITE_URL,
        }, status_code=404)
    if exc.status_code == 500:
        logger.error(f"Internal server error: {exc.detail}")
    return HTMLResponse(
        content=f"<h1>Error {exc.status_code}</h1><p>{exc.detail or 'Something went wrong.'}</p>",
        status_code=exc.status_code,
    )


# ── Catch-all for unmatched routes ────────────────────────────
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def catch_all(request: Request, path: str):
    stats = get_db_stats()
    return templates.TemplateResponse("404.html", {
        "request": request,
        "stats": stats,
        "meta_description": "Page not found. Search anime figurines across 8 stores on Figurya.",
        "og_title": "Page Not Found | Figurya",
        "canonical_url": SITE_URL,
    }, status_code=404)


def main():
    """Entry point for the CLI script."""
    import uvicorn
    uvicorn.run("weebshelf.app:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()
