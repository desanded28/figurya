import httpx
from weebshelf.fetchers.base import BaseFetcher, JSON_HEADERS, logger
from weebshelf.models import Figurine
from weebshelf.config import MAX_RESULTS_PER_SOURCE


class SolarisFetcher(BaseFetcher):
    name = "Solaris Japan"
    BASE_URL = "https://solarisjapan.com"

    async def _fetch(self, query: str) -> list[Figurine]:
        url = f"{self.BASE_URL}/search/suggest.json"
        params = {
            "q": query,
            "resources[type]": "product",
            "resources[limit]": "10",
        }

        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, params=params, headers=JSON_HEADERS)
            if resp.status_code != 200:
                logger.warning(f"[{self.name}] Status {resp.status_code}")
                return []
            return self._parse_results(resp.json())

    def _parse_results(self, data: dict) -> list[Figurine]:
        figures = []
        try:
            products = data.get("resources", {}).get("results", {}).get("products", [])
        except (AttributeError, TypeError):
            return []

        for product in products[:MAX_RESULTS_PER_SOURCE]:
            try:
                name = product.get("title", "").strip()
                if not name:
                    continue

                price_str = product.get("price", "0")
                try:
                    price = float(str(price_str).replace(",", ""))
                except (ValueError, TypeError):
                    price = None
                if price == 0:
                    price = None

                image_url = self.make_absolute(product.get("image", ""), self.BASE_URL)
                product_url = self.make_absolute(product.get("url", ""), self.BASE_URL)

                available = product.get("available", True)

                fig = Figurine(
                    name=name,
                    product_url=product_url,
                    image_url=image_url,
                    store=self.name,
                    price=price,
                    currency="USD",
                    availability="in_stock" if available else "sold_out",
                    tags=self.extract_tags(name),
                    description=name,
                )
                figures.append(fig)
            except Exception as e:
                logger.error(f"[{self.name}] Parse error: {e}")
                continue

        return figures
