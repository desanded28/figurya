import httpx
from bs4 import BeautifulSoup
from weebshelf.fetchers.base import BaseFetcher, DEFAULT_HEADERS, logger
from weebshelf.models import Figurine
from weebshelf.config import MAX_RESULTS_PER_SOURCE
import re


class GoodSmileFetcher(BaseFetcher):
    """Fetches figurine data from Good Smile Company."""
    name = "Good Smile"
    BASE_URL = "https://www.goodsmile.info"

    async def _fetch(self, query: str) -> list[Figurine]:
        url = f"{self.BASE_URL}/en/products/search"
        params = {
            "utf8": "✓",
            "search_query": query,
        }

        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(url, params=params, headers=DEFAULT_HEADERS)
            if resp.status_code != 200:
                logger.warning(f"[{self.name}] Status {resp.status_code}")
                return []
            return self._parse_results(resp.text)

    def _parse_results(self, html: str) -> list[Figurine]:
        soup = BeautifulSoup(html, "html.parser")
        cards = (
            soup.select(".hitItem")
            or soup.select(".product-item")
            or soup.select('[class*="product"]')
            or soup.select(".resultItem")
        )
        figures = []

        for card in cards[:MAX_RESULTS_PER_SOURCE]:
            try:
                title_el = (
                    card.select_one(".hitTtl a")
                    or card.select_one("a[title]")
                    or card.select_one("h3 a")
                    or card.select_one("a")
                )
                if not title_el:
                    continue
                name = title_el.get("title", "") or title_el.get_text(strip=True)
                if not name:
                    continue

                href = title_el.get("href", "")
                product_url = self.make_absolute(href, self.BASE_URL)

                img = card.select_one("img")
                img_url = ""
                if img:
                    img_url = img.get("src", "") or img.get("data-src", "")
                    img_url = self.make_absolute(img_url, self.BASE_URL)

                # Good Smile is manufacturer — prices are MSRP in JPY
                price = None
                price_el = card.select_one(".hitPrice") or card.select_one('[class*="price"]')
                if price_el:
                    price_match = re.search(r"[\d,]+", price_el.get_text().replace("¥", ""))
                    if price_match:
                        try:
                            price = float(price_match.group().replace(",", ""))
                        except ValueError:
                            pass

                fig = Figurine(
                    name=name,
                    product_url=product_url,
                    image_url=img_url,
                    store=self.name,
                    price=price,
                    currency="JPY",
                    availability="unknown",
                    tags=self.extract_tags(name),
                    description=name,
                )
                figures.append(fig)
            except Exception as e:
                logger.error(f"[{self.name}] Parse error: {e}")
                continue

        return figures
