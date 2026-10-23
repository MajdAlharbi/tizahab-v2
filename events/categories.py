from __future__ import annotations


TOURISM_CATEGORY_CHOICES = [
    ("culture", "Culture"),
    ("heritage", "Heritage"),
    ("entertainment", "Entertainment"),
    ("food", "Food"),
    ("shopping", "Shopping"),
    ("nature", "Nature"),
    ("family", "Family"),
    ("events", "Events"),
]

TOURISM_CATEGORY_VALUES = [value for value, _ in TOURISM_CATEGORY_CHOICES]

LEGACY_CATEGORY_ALIASES = {
    "restaurant": "food",
    "cafe": "food",
    "fast_food": "food",
    "dessert": "food",
    "bakery": "food",
    "juice": "food",
    "food_truck": "food",
    "outdoor": "nature",
    "other": "entertainment",
    "mall": "shopping",
    "museum": "heritage",
}

CATEGORY_INPUT_MAP = {
    **{value: value for value in TOURISM_CATEGORY_VALUES},
    **LEGACY_CATEGORY_ALIASES,
}

KEYWORD_CATEGORY_RULES = [
    (
        "heritage",
        (
            "heritage",
            "museum",
            "historic",
            "history",
            "fort",
            "palace",
            "souq",
        ),
    ),
    (
        "events",
        (
            "event",
            "festival",
            "concert",
            "show",
            "expo",
            "exhibition",
            "season",
            "celebration",
        ),
    ),
    (
        "family",
        (
            "family",
            "kids",
            "children",
            "play",
            "playground",
            "zoo",
            "aquarium",
        ),
    ),
    (
        "nature",
        (
            "park",
            "garden",
            "wadi",
            "desert",
            "trail",
            "nature",
        ),
    ),
    (
        "shopping",
        (
            "mall",
            "shopping",
            "market",
            "boutique",
            "store",
        ),
    ),
    (
        "culture",
        (
            "culture",
            "art",
            "gallery",
            "library",
            "theatre",
            "theater",
        ),
    ),
    (
        "food",
        (
            "restaurant",
            "cafe",
            "coffee",
            "food",
            "dining",
            "burger",
            "bakery",
        ),
    ),
    (
        "entertainment",
        (
            "cinema",
            "game",
            "fun",
            "amusement",
            "bowling",
            "escape room",
        ),
    ),
]


def normalize_category(raw_category, title="", description=""):
    normalized = str(raw_category or "").strip().lower()
    if normalized in TOURISM_CATEGORY_VALUES:
        return normalized
    if normalized in LEGACY_CATEGORY_ALIASES:
        return LEGACY_CATEGORY_ALIASES[normalized]

    haystack = f"{title} {description} {normalized}".lower()
    for target_category, keywords in KEYWORD_CATEGORY_RULES:
        if any(keyword in haystack for keyword in keywords):
            return target_category

    return "events"


def normalize_category_input(raw_category):
    normalized = str(raw_category or "").strip().lower()
    return CATEGORY_INPUT_MAP.get(normalized)
