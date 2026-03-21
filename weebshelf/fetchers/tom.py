import httpx
from weebshelf.fetchers.base import BaseFetcher, JSON_HEADERS, logger
from weebshelf.models import Figurine
from weebshelf.config import MAX_RESULTS_PER_SOURCE


class TOMFetcher(BaseFetcher):
    name = "Tokyo Otaku Mode"
    BASE_URL = "https://otakumode.com"

    async def _fetch(self, query: str) -> list[Figurine]:
        url = f"{self.BASE_URL}/search/api/products"
        params = {
            "mode": "shop",
            "keyword": query,
            "limit": "20",
        }

        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, params=params, headers=JSON_HEADERS)
            if resp.status_code != 200:
                logger.warning(f"[{self.name}] Status {resp.status_code}")
                return []
            return self._parse_results(resp.json())

    def _parse_results(self, data: dict) -> list[Figurine]:
        figures = []
        products = data if isinstance(data, list) else data.get("products", data.get("items", []))

        for product in products[:MAX_RESULTS_PER_SOURCE]:
            try:
                name = product.get("title", "").strip()
                if not name:
                    continue

                prices = product.get("prices", {})
                price = prices.get("min_selling") or prices.get("min") or None
                if price is not None:
                    try:
                        price = float(price)
                    except (ValueError, TypeError):
                        price = None

                main_image = product.get("main_image", {})
                image_source = main_image.get("source", "") if isinstance(main_image, dict) else ""
                image_url = image_source
                if image_url and not image_url.startswith("http"):
                    image_url = "https://resize.cdn.otakumode.com/full" + image_url

                product_url = self.make_absolute(product.get("url", ""), self.BASE_URL)

                is_oos = product.get("is_out_of_stock", False)
                is_disc = product.get("is_discontinued", False)
                if is_disc or is_oos:
                    availability = "sold_out"
                else:
                    availability = "in_stock"

                fig = Figurine(
                    name=name,
                    product_url=product_url,
                    image_url=image_url,
                    store=self.name,
                    price=price,
                    currency="USD",
                    availability=availability,
                    tags=self.extract_tags(name),
                    description=name,
                )
                figures.append(fig)
            except Exception as e:
                logger.error(f"[{self.name}] Parse error: {e}")
                continue

        return figures
