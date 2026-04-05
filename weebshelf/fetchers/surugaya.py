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
        url = f"{self.BASE_URL}/en/products"
        params = {"search_word": f"{query} figure"}

        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(url, params=params, headers=DEFAULT_HEADERS)
            if resp.status_code != 200:
                logger.warning(f"[{self.name}] Status {resp.status_code}")
                return []
            return self._parse_results(resp.text)

    def _parse_results(self, html: str) -> list[Figurine]:
        soup = BeautifulSoup(html, "html.parser")
        items = soup.select(".item.col-12")
        figures = []

        for item in items[:MAX_RESULTS_PER_SOURCE]:
            try:
                # Name (prefer alt attribute on image, fallback to title link text)
                img = item.select_one("img")
                name = ""
                if img:
                    name = img.get("alt", "").strip()
                if not name:
                    title_link = item.select_one(".title_product a")
                    if title_link:
                        name = title_link.get_text(strip=True)
                if not name:
                    continue

                # URL
                link = item.select_one(".title_product a") or item.select_one("a[href*='/product/']")
                if not link:
                    continue
                product_url = self.make_absolute(link.get("href", ""), self.BASE_URL)

                # Image
                img_url = ""
                if img:
                    img_url = img.get("src", "") or img.get("data-src", "")
                    img_url = self.make_absolute(img_url, self.BASE_URL)

                # Price (JPY)
                price = None
                price_el = item.select_one(".price-new") or item.select_one(".price_product")
                if price_el:
                    price_text = price_el.get_text()
                    price_match = re.search(r"[\d,]+", price_text)
                    if price_match:
                        try:
                            price = float(price_match.group().replace(",", ""))
                        except ValueError:
                            pass

                # Used vs new
                is_used = bool(item.select_one(".icon_used"))
                tags = self.extract_tags(name)
                if is_used:
                    tags.append("pre-owned")

                fig = Figurine(
                    name=name,
                    product_url=product_url,
                    image_url=img_url,
                    store=self.name,
                    price=price,
                    currency="JPY",
                    availability="in_stock",
                    tags=tags,
                    description=name,
                )
                figures.append(fig)
            except Exception as e:
                logger.error(f"[{self.name}] Parse error: {e}")
                continue

        return figures
