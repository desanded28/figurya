from weebshelf.config import COLORS, AESTHETICS, SCALES


def parse_query(raw_query: str) -> dict:
    """Split query into character, colors, aesthetics, and scale types."""
    # Sanitize: truncate, normalize whitespace
    import unicodedata
    raw_query = unicodedata.normalize("NFKC", raw_query)[:200]
    tokens = raw_query.lower().strip().split()

    colors = [t for t in tokens if t in COLORS]
    aesthetics = [t for t in tokens if t in AESTHETICS]

    scale_matches = []
    remaining = []
    i = 0
    while i < len(tokens):
        # Check two-word scales like "pop up parade"
        three_word = " ".join(tokens[i:i+3]) if i+2 < len(tokens) else ""
        two_word = " ".join(tokens[i:i+2]) if i+1 < len(tokens) else ""

        if three_word in SCALES:
            scale_matches.append(three_word)
            i += 3
        elif two_word in SCALES:
            scale_matches.append(two_word)
            i += 2
        elif tokens[i] in SCALES:
            scale_matches.append(tokens[i])
            i += 1
        elif tokens[i] not in COLORS and tokens[i] not in AESTHETICS:
            remaining.append(tokens[i])
            i += 1
        else:
            i += 1

    character = " ".join(remaining)

    return {
        "raw": raw_query.strip(),
        "character": character,
        "colors": colors,
        "aesthetics": aesthetics,
        "scales": scale_matches,
    }


def build_search_terms(parsed: dict) -> str:
    """Build the search string to send to fetchers."""
    parts = []
    if parsed["character"]:
        parts.append(parsed["character"])
    for s in parsed["scales"]:
        parts.append(s)
    return " ".join(parts) if parts else parsed["raw"]
