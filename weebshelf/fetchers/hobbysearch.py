import httpx
from bs4 import BeautifulSoup
from weebshelf.fetchers.base import BaseFetcher, DEFAULT_HEADERS, logger
from weebshelf.models import Figurine
from weebshelf.config import MAX_RESULTS_PER_SOURCE
import re


class HobbySearchFetcher(BaseFetcher):
    name = "HobbySearch"
    BASE_URL = "https://www.1999.co.jp"

    async def _fetch(self, query: str) -> list[Figurine]:
        search_url = f"{self.BASE_URL}/eng/search"
        params = {
            "typ1_c": "101",
            "cat": "",
            "target": "SeriesTitle",
            "searchkey": query,
            "qty": str(MAX_RESULTS_PER_SOURCE),
        }

        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(search_url, params=params, headers=DEFAULT_HEADERS)
            if resp.status_code != 200:
                logger.info(f"[{self.name}] Status {resp.status_code}")
                return []
            return self._parse_results(resp.text)

    def _parse_results(self, html: str) -> list[Figurine]:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select(".c-card")
        figures = []

        for card in cards[:MAX_RESULTS_PER_SOURCE]:
            try:
                img = card.select_one('img[src*="/itbig"]') or card.select_one('img[src*="/itsmall"]')
                if not img:
                    continue
                name = img.get("alt", "").strip()
                if not name:
                    continue

                img_src = self.make_absolute(img.get("src", ""), self.BASE_URL)

                price_el = card.select_one('[class*=price]')
                price_text = price_el.get_text(strip=True) if price_el else ""
                price_match = re.search(r"([\d,]+)\s*JPY", price_text)
                price = int(price_match.group(1).replace(",", "")) if price_match else None

                link_el = card.select_one('a[href*="/eng/1"]')
                href = link_el.get("href", "") if link_el else ""
                product_url = self.make_absolute(href, self.BASE_URL)

                card_text = card.get_text()
                availability = "unknown"
                if "In Stock" in card_text:
                    availability = "in_stock"
                elif "Back-order" in card_text or "Pre-order" in card_text:
                    availability = "preorder"
                elif "Sold Out" in card_text:
                    availability = "sold_out"

                fig = Figurine(
                    name=name,
                    product_url=product_url,
                    image_url=img_src,
                    store=self.name,
                    price=price,
                    currency="JPY",
                    availability=availability,
                    tags=self.extract_tags(name),
                    description=name,
                )
                figures.append(fig)
            except Exception as e:
                logger.error(f"[{self.name}] Parse error: {e}")
                continue

        return figures
