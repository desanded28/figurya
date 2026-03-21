import httpx
from bs4 import BeautifulSoup
from weebshelf.fetchers.base import BaseFetcher, DEFAULT_HEADERS, logger
from weebshelf.models import Figurine
from weebshelf.config import MAX_RESULTS_PER_SOURCE
import re


class AmazonFetcher(BaseFetcher):
    name = "Amazon"
    BASE_URL = "https://www.amazon.com"

    async def _fetch(self, query: str) -> list[Figurine]:
        search_url = f"{self.BASE_URL}/s"
        params = {
            "k": f"{query} figure",
            "i": "toys-and-games",
        }

        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(search_url, params=params, headers=DEFAULT_HEADERS)
            if resp.status_code != 200:
                logger.warning(f"[{self.name}] Status {resp.status_code}")
                return []
            if "captcha" in resp.text.lower()[:2000] or "robot" in resp.text.lower()[:2000]:
                logger.info(f"[{self.name}] Captcha detected, skipping")
                return []
            return self._parse_results(resp.text)

    def _parse_results(self, html: str) -> list[Figurine]:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select('[data-component-type="s-search-result"]')
        figures = []

        for card in cards[:MAX_RESULTS_PER_SOURCE]:
            try:
                title_el = card.select_one("h2 a span") or card.select_one("h2 span")
                if not title_el:
                    continue
                name = title_el.get_text(strip=True)
                if not name:
                    continue

                link = card.select_one("h2 a[href]")
                href = ""
                if link:
                    href = link.get("href", "")
                    if href and not href.startswith("http"):
                        href = self.BASE_URL + href
                    href = re.sub(r"\?.*", "", href) if "/dp/" in href else href

                img = card.select_one("img.s-image")
                img_src = img.get("src", "") if img else ""

                price = None
                price_whole = card.select_one(".a-price-whole")
                price_frac = card.select_one(".a-price-fraction")
                if price_whole:
                    pw = price_whole.get_text(strip=True).replace(",", "").replace(".", "")
                    pf = price_frac.get_text(strip=True) if price_frac else "00"
                    try:
                        price = float(f"{pw}.{pf}")
                    except (ValueError, TypeError):
                        pass

                rating = None
                rating_el = card.select_one(".a-icon-star-small .a-icon-alt")
                if rating_el:
                    rating_match = re.search(r"([\d.]+)", rating_el.get_text())
                    if rating_match:
                        rating = float(rating_match.group(1)) * 2

                name_lower = name.lower()
                skip_words = ["poster", "sticker", "keychain", "phone case", "t-shirt", "shirt"]
                if any(w in name_lower for w in skip_words) and "figure" not in name_lower:
                    continue

                fig = Figurine(
                    name=name,
                    product_url=href,
                    image_url=img_src,
                    store=self.name,
                    price=price,
                    currency="USD",
                    availability="in_stock",
                    rating=rating,
                    tags=self.extract_tags(name),
                    description=name,
                )
                figures.append(fig)
            except Exception as e:
                logger.error(f"[{self.name}] Parse error: {e}")
                continue

        return figures
