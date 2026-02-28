import httpx
from weebshelf.fetchers.base import BaseFetcher
from weebshelf.models import Figurine
from weebshelf.config import MAX_RESULTS_PER_SOURCE


class TOMFetcher(BaseFetcher):
    """Fetches figurine data from Tokyo Otaku Mode (JSON API)."""
    name = "Tokyo Otaku Mode"
    BASE_URL = "https://otakumode.com"

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
    }

    async def search(self, query: str) -> list[Figurine]:
        url = f"{self.BASE_URL}/search/api/products"
        params = {
            "mode": "shop",
            "keyword": query,
            "limit": "20",
        }

        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url, params=params, headers=self.HEADERS)
                if resp.status_code != 200:
                    print(f"[TOM] Status {resp.status_code}")
                    return []
                return self._parse_results(resp.json())
        except Exception as e:
            print(f"[TOM] Error: {e}")
            return []

    def _parse_results(self, data: dict) -> list[Figurine]:
        figures = []
        products = data if isinstance(data, list) else data.get("products", data.get("items", []))

        for product in products[:MAX_RESULTS_PER_SOURCE]:
            try:
                name = product.get("title", "").strip()
                if not name:
                    continue

                # Price
                prices = product.get("prices", {})
                price = prices.get("min_selling") or prices.get("min") or None
                if price is not None:
                    try:
                        price = float(price)
                    except (ValueError, TypeError):
                        price = None

                # Image
                main_image = product.get("main_image", {})
                image_source = main_image.get("source", "") if isinstance(main_image, dict) else ""
                image_url = image_source
                if image_url and not image_url.startswith("http"):
                    image_url = "https://resize.cdn.otakumode.com/full" + image_url

                # URL
                rel_url = product.get("url", "")
                product_url = self.BASE_URL + rel_url if rel_url.startswith("/") else rel_url

                # Availability
                is_oos = product.get("is_out_of_stock", False)
                is_disc = product.get("is_discontinued", False)
                if is_disc:
                    availability = "sold_out"
                elif is_oos:
                    availability = "sold_out"
                else:
                    availability = "in_stock"

                tags = []
                name_lower = name.lower()
                for tag_word in ["nendoroid", "figma", "scale", "prize", "pop up parade",
                                 "figure", "statue"]:
                    if tag_word in name_lower:
                        tags.append(tag_word)

                fig = Figurine(
                    name=name,
                    product_url=product_url,
                    image_url=image_url,
                    store="Tokyo Otaku Mode",
                    price=price,
                    currency="USD",
                    availability=availability,
                    tags=tags,
                    description=name,
                )
                figures.append(fig)
            except Exception as e:
                print(f"[TOM] Parse error: {e}")
                continue

        return figures
