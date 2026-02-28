from weebshelf.models import Figurine, SearchResult
from weebshelf.config import STORE_RELIABILITY


def compute_keyword_relevance(figurine: Figurine, parsed_query: dict) -> tuple[float, list[str]]:
    """Score how well a figurine matches the query's colors/aesthetics/keywords."""
    name_lower = figurine.name.lower()
    desc_lower = figurine.description.lower()
    tags_lower = " ".join(figurine.tags).lower()
    combined = f"{name_lower} {desc_lower} {tags_lower}"

    score = 0.0
    matches = []

    # Character name match (most important)
    character = parsed_query.get("character", "")
    if character and character.lower() in combined:
        score += 0.5
        matches.append(f"character: {character}")

    # Color matches
    for color in parsed_query.get("colors", []):
        if color in combined:
            score += 0.15
            matches.append(f"color: {color}")

    # Aesthetic matches
    for aesthetic in parsed_query.get("aesthetics", []):
        if aesthetic in combined:
            score += 0.15
            matches.append(f"style: {aesthetic}")
        # Check related terms
        related = AESTHETIC_RELATIONS.get(aesthetic, [])
        for rel in related:
            if rel in combined:
                score += 0.08
                matches.append(f"~{aesthetic}: {rel}")
                break

    # Scale matches
    for scale in parsed_query.get("scales", []):
        if scale in combined:
            score += 0.1
            matches.append(f"type: {scale}")

    return min(score, 1.0), matches


# Map aesthetic keywords to related terms that might appear in descriptions
AESTHETIC_RELATIONS = {
    "girly": ["cute", "pink", "ribbon", "dress", "flower", "heart", "sweet", "princess"],
    "gothic": ["dark", "black", "lolita", "cross", "skull", "demon", "vampire"],
    "cute": ["kawaii", "chibi", "smile", "small", "mini", "adorable"],
    "elegant": ["dress", "formal", "gown", "beautiful", "graceful", "refined"],
    "sexy": ["bikini", "swimsuit", "bunny", "revealing", "adult"],
    "cool": ["action", "dynamic", "sword", "battle", "pose", "fighting"],
    "kawaii": ["cute", "chibi", "pastel", "smile", "adorable", "sweet"],
    "dark": ["gothic", "black", "shadow", "demon", "evil", "villain"],
    "sporty": ["athletic", "uniform", "racing", "sports", "active"],
    "magical": ["witch", "wand", "magic", "spell", "fairy", "fantasy"],
}


def get_reliability(store: str) -> float:
    return STORE_RELIABILITY.get(store, STORE_RELIABILITY["default"])


def rank_results(figurines: list[Figurine], parsed_query: dict) -> list[SearchResult]:
    """Rank figurines by composite score."""
    results = []

    for fig in figurines:
        relevance, matches = compute_keyword_relevance(fig, parsed_query)
        reliability = get_reliability(fig.store)

        # Price competitiveness (normalized, lower is better)
        price_score = 0.5  # default for unknown price
        if fig.price_usd is not None:
            # Rough normalization: $0 = 1.0, $300+ = 0.0
            price_score = max(0, 1.0 - (fig.price_usd / 300))

        # Availability score
        avail_map = {"in_stock": 1.0, "preorder": 0.8, "unknown": 0.4, "sold_out": 0.1}
        availability = avail_map.get(fig.availability, 0.4)

        # Community rating (0-10 -> 0-1)
        rating_score = (fig.rating / 10) if fig.rating else 0.5

        final = (
            0.35 * relevance
            + 0.25 * reliability
            + 0.20 * price_score
            + 0.10 * availability
            + 0.10 * rating_score
        )

        results.append(SearchResult(
            figurine=fig,
            relevance_score=round(relevance, 3),
            keyword_matches=matches,
            reliability_score=reliability,
            final_score=round(final, 3),
        ))

    results.sort(key=lambda r: r.final_score, reverse=True)
    return results
