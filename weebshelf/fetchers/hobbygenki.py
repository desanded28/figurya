from bs4 import BeautifulSoup
from weebshelf.fetchers.base import BaseFetcher, DEFAULT_HEADERS, logger, oracle_proxied_get
from weebshelf.models import Figurine
from weebshelf.config import MAX_RESULTS_PER_SOURCE
import re


class HobbyGenkiFetcher(BaseFetcher):
    name = "Hobby Genki"
    BASE_URL = "https://hobby-genki.com"

    async def _fetch(self, query: str) -> list[Figurine]:
        url = f"{self.BASE_URL}/en/search"
        params = {
            "controller": "search",
            "s": query,
        }

        resp = await oracle_proxied_get(url, params=params, headers=DEFAULT_HEADERS)
        if resp.status_code != 200:
            logger.warning(f"[{self.name}] Status {resp.status_code}")
            return []
        return self._parse_results(resp.text)

    def _parse_results(self, html: str) -> list[Figurine]:
        soup = BeautifulSoup(html, "html.parser")
        figures = []

        articles = soup.select("article.product-miniature")

        for article in articles[:MAX_RESULTS_PER_SOURCE]:
            try:
                title_el = article.select_one(".product-title a")
                if not title_el:
                    continue
                name = title_el.get_text(strip=True)
                if not name:
                    continue
                href = title_el.get("href", "")

                img = article.select_one("img")
                img_src = ""
                if img:
                    img_src = img.get("data-full-size-image-url", "") or img.get("src", "")
                    img_src = self.make_absolute(img_src, self.BASE_URL)

                price = None
                price_el = article.select_one(".product-price-and-shipping .price")
                if price_el:
                    price_text = price_el.get_text(strip=True)
                    match = re.search(r"[¥]?\s*([\d,]+)", price_text)
                    if match:
                        price = int(match.group(1).replace(",", ""))

                flags = article.select(".product-flag")
                flag_texts = [f.get_text(strip=True).lower() for f in flags]
                availability = "in_stock"
                if any("sold" in f or "out" in f for f in flag_texts):
                    availability = "sold_out"
                elif any("pre" in f for f in flag_texts):
                    availability = "preorder"

                discount_el = article.select_one(".discount-percentage")
                discount = discount_el.get_text(strip=True) if discount_el else ""
                extra_tags = [f"sale {discount}"] if discount else None

                fig = Figurine(
                    name=name,
                    product_url=href,
                    image_url=img_src,
                    store=self.name,
                    price=price,
                    currency="JPY",
                    availability=availability,
                    tags=self.extract_tags(name, extra_tags),
                    description=name,
                )
                figures.append(fig)
            except Exception as e:
                logger.error(f"[{self.name}] Parse error: {e}")
                continue

        return figures
