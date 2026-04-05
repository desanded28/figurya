import httpx
from bs4 import BeautifulSoup
from weebshelf.fetchers.base import BaseFetcher, DEFAULT_HEADERS, logger
from weebshelf.models import Figurine
from weebshelf.config import MAX_RESULTS_PER_SOURCE
import re


class AnimateFetcher(BaseFetcher):
    name = "Animate"
    BASE_URL = "https://www.animate-onlineshop.jp"

    async def _fetch(self, query: str) -> list[Figurine]:
        url = f"{self.BASE_URL}/products/list.php"
        params = {"smt": query}

        headers = {**DEFAULT_HEADERS, "Accept-Language": "ja,en-US;q=0.9,en;q=0.8"}

        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(url, params=params, headers=headers)
            if resp.status_code != 200:
                logger.warning(f"[{self.name}] Status {resp.status_code}")
                return []
            return self._parse_results(resp.text)

    def _parse_results(self, html: str) -> list[Figurine]:
        soup = BeautifulSoup(html, "html.parser")
        items = soup.select(".item_list ul li")
        figures = []

        for item in items[:MAX_RESULTS_PER_SOURCE]:
            try:
                link = item.select_one("h3 a") or item.select_one(".item_list_thumb a")
                if not link:
                    continue

                name = link.get("title", "") or link.get_text(strip=True)
                if not name:
                    continue

                product_url = self.make_absolute(link.get("href", ""), self.BASE_URL)

                img = item.select_one("img")
                img_url = ""
                if img:
                    img_url = img.get("src", "") or img.get("data-src", "")
                    img_url = self.make_absolute(img_url, self.BASE_URL)

                # Price (JPY) — format: "2,420円(税込)"
                price = None
                price_el = item.select_one(".price font") or item.select_one(".price")
                if price_el:
                    price_text = price_el.get_text()
                    price_match = re.search(r"[\d,]+", price_text)
                    if price_match:
                        try:
                            price = float(price_match.group().replace(",", ""))
                        except ValueError:
                            pass

                # Stock status
                stock_el = item.select_one(".stock")
                availability = "in_stock"
                if stock_el and "販売終了" in stock_el.get_text():
                    availability = "out_of_stock"

                fig = Figurine(
                    name=name,
                    product_url=product_url,
                    image_url=img_url,
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
