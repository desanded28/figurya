from collections import Counter
from weebshelf.models import Review

POSITIVE_WORDS = {
    "great", "amazing", "beautiful", "excellent", "perfect", "stunning",
    "detailed", "gorgeous", "lovely", "fantastic", "incredible", "superb",
    "quality", "worth", "recommend", "love", "best", "good", "nice",
    "vibrant", "accurate", "faithful", "sculpt", "dynamic",
}

NEGATIVE_WORDS = {
    "bad", "poor", "cheap", "flimsy", "broken", "defect", "disappointed",
    "overpriced", "fragile", "lean", "leaning", "loose", "paint",
    "shipping", "damage", "wrong", "missing", "worst", "awful",
    "terrible", "ugly", "bland", "boring", "plain",
}


def summarize_reviews(reviews: list[Review]) -> str:
    if not reviews:
        return ""

    positives = []
    negatives = []

    for review in reviews:
        words = set(review.text.lower().split())
        for w in words & POSITIVE_WORDS:
            positives.append(w)
        for w in words & NEGATIVE_WORDS:
            negatives.append(w)

    parts = []

    if positives:
        top_pos = [w for w, _ in Counter(positives).most_common(3)]
        parts.append(f"Praised for: {', '.join(top_pos)}")

    if negatives:
        top_neg = [w for w, _ in Counter(negatives).most_common(3)]
        parts.append(f"Criticized for: {', '.join(top_neg)}")

    if reviews[0].rating is not None:
        ratings = [r.rating for r in reviews if r.rating is not None]
        if ratings:
            avg = sum(ratings) / len(ratings)
            parts.append(f"Avg rating: {avg:.1f}/10 ({len(ratings)} reviews)")

    return " | ".join(parts) if parts else "No detailed reviews available"
