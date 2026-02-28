from pydantic import BaseModel
from typing import Optional


class Review(BaseModel):
    username: str = "Anonymous"
    rating: Optional[float] = None  # 0-10 scale
    text: str = ""


class Figurine(BaseModel):
    name: str
    character: str = ""
    series: str = ""
    manufacturer: str = ""
    price: Optional[float] = None
    currency: str = "JPY"
    image_url: str = ""
    product_url: str = ""
    store: str = ""
    availability: str = "unknown"  # in_stock, preorder, sold_out, unknown
    rating: Optional[float] = None  # 0-10
    tags: list[str] = []
    reviews: list[Review] = []
    description: str = ""

    @property
    def price_usd(self) -> Optional[float]:
        if self.price is None:
            return None
        if self.currency == "USD":
            return self.price
        if self.currency == "JPY":
            return round(self.price / 150, 2)  # rough conversion
        return self.price

    @property
    def display_price(self) -> str:
        if self.price is None:
            return "N/A"
        if self.currency == "JPY":
            return f"¥{self.price:,.0f} (~${self.price_usd:,.2f})"
        return f"${self.price:,.2f}"


class SearchResult(BaseModel):
    figurine: Figurine
    relevance_score: float = 0.0
    keyword_matches: list[str] = []
    review_summary: str = ""
    reliability_score: float = 0.5  # 0-1, store trustworthiness
    final_score: float = 0.0
