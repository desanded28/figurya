import httpx
from bs4 import BeautifulSoup
from weebshelf.fetchers.base import BaseFetcher, DEFAULT_HEADERS, logger
from weebshelf.models import Figurine
from weebshelf.config import MAX_RESULTS_PER_SOURCE
import re


class SurugayaFetcher(BaseFetcher):
    name = "Suruga-ya"
    BASE_URL = "https://www.suruga-ya.com"

    async def _fetch(self, query: str) -> list[Figurine]:
        url = f"{self.BASE_URL}/en/search"
        params = {
            "category": "",
            "search_word": f"{query} figure",
        }

        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(url, params=params, headers=DEFAULT_HEADERS)
            if resp.status_code != 200:
                logger.warning(f"[{self.name}] Status {resp.status_code}")
                return []
            return self._parse_results(resp.text)

    def _parse_results(self, html: str) -> list[Figurine]:
        soup = BeautifulSoup(html, "html.parser")
        items = soup.select(".item") or soup.select(".product_box") or soup.select('[class*="item"]')
        figures = []

        for item in items[:MAX_RESULTS_PER_SOURCE]:
            try:
                # Title
                title_el = item.select_one("a[title]") or item.select_one(".title a") or item.select_one("a")
                if not title_el:
                    continue
                name = title_el.get("title", "") or title_el.get_text(strip=True)
                if not name:
                    continue

                # URL
                href = title_el.get("href", "")
                product_url = self.make_absolute(href, self.BASE_URL)

                # Image
                img = item.select_one("img")
                img_url = ""
                if img:
                    img_url = img.get("src", "") or img.get("data-src", "")
                    img_url = self.make_absolute(img_url, self.BASE_URL)

                # Price (JPY)
                price = None
                price_el = item.select_one(".price") or item.select_one('[class*="price"]')
                if price_el:
                    price_text = price_el.get_text()
                    price_match = re.search(r"[\d,]+", price_text.replace("¥", ""))
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
                    availability="in_stock",  # Suruga-ya mostly lists available items
                    tags=self.extract_tags(name, ["pre-owned"]),
                    description=name,
                )
                figures.append(fig)
            except Exception as e:
                logger.error(f"[{self.name}] Parse error: {e}")
                continue

        return figures
