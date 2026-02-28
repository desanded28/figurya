import httpx
from weebshelf.fetchers.base import BaseFetcher
from weebshelf.models import Figurine
from weebshelf.config import MAX_RESULTS_PER_SOURCE


class SolarisFetcher(BaseFetcher):
    """Fetches figurine data from Solaris Japan (Shopify JSON API)."""
    name = "Solaris Japan"
    BASE_URL = "https://solarisjapan.com"

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
    }

    async def search(self, query: str) -> list[Figurine]:
        url = f"{self.BASE_URL}/search/suggest.json"
        params = {
            "q": query,
            "resources[type]": "product",
            "resources[limit]": "10",
        }

        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url, params=params, headers=self.HEADERS)
                if resp.status_code != 200:
                    print(f"[Solaris] Status {resp.status_code}")
                    return []
                return self._parse_results(resp.json())
        except Exception as e:
            print(f"[Solaris] Error: {e}")
            return []

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

                image_url = product.get("image", "")
                if image_url and image_url.startswith("//"):
                    image_url = "https:" + image_url

                rel_url = product.get("url", "")
                product_url = self.BASE_URL + rel_url if rel_url.startswith("/") else rel_url

                available = product.get("available", True)

                tags = []
                name_lower = name.lower()
                for tag_word in ["nendoroid", "figma", "scale", "prize", "pop up parade",
                                 "figure", "statue", "pvc"]:
                    if tag_word in name_lower:
                        tags.append(tag_word)

                fig = Figurine(
                    name=name,
                    product_url=product_url,
                    image_url=image_url,
                    store="Solaris Japan",
                    price=price,
                    currency="USD",
                    availability="in_stock" if available else "sold_out",
                    tags=tags,
                    description=name,
                )
                figures.append(fig)
            except Exception as e:
                print(f"[Solaris] Parse error: {e}")
                continue

        return figures
