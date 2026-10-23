#!/usr/bin/env python3
import json
import os
import sys
from datetime import timedelta
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.utils import timezone  # noqa: E402

from events.models import Event  # noqa: E402


DATA_DIR = BASE_DIR / "data"
DATASET_FILES = [
    "culture_dataset.json",
    "heritage_dataset.json",
    "entertainment_dataset.json",
    "food_dataset.json",
    "shopping_dataset.json",
    "nature_dataset.json",
    "family_dataset.json",
    "events_dataset.json",
]


def to_float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_title(value):
    return " ".join(str(value or "").strip().split())


def normalize_category(item, fallback_category):
    raw_category = item.get("category")
    if not raw_category and "family" in item:
        raw_category = item.get("family")
    if not raw_category:
        raw_category = fallback_category
    return str(raw_category or fallback_category).strip().lower()


def normalize_item(item, fallback_category, index, base_date):
    title = normalize_title(item.get("title") or item.get("name"))
    if not title:
        return None

    latitude = to_float(item.get("latitude"))
    longitude = to_float(item.get("longitude"))
    if latitude is None or longitude is None:
        return None

    rating = to_float(item.get("rating"), default=4.0)
    rating = max(0.0, min(5.0, rating))

    category = normalize_category(item, fallback_category)

    return {
        "title": title,
        "category": category,
        "description": item.get("description") or f"{title} in Riyadh",
        "date": base_date + timedelta(minutes=index),
        "location": item.get("location") or "Riyadh, Saudi Arabia",
        "rating": round(rating, 1),
        "latitude": latitude,
        "longitude": longitude,
        "source": "data_loader",
        "source_url": "",
        "is_active": True,
        "tourism_relevance": 3,
    }


def load_json_file(path):
    with path.open(encoding="utf-8") as source_file:
        data = json.load(source_file)
    if isinstance(data, list):
        return data
    return []


def main():
    print("Initializing Django data load...")

    missing_files = []
    total_inserted = 0
    skipped_duplicates = 0
    skipped_invalid = 0
    seen_titles = set()
    base_date = timezone.now()

    deleted_count, _ = Event.objects.all().delete()
    print(f"Deleted existing Event records: {deleted_count}")

    for file_name in DATASET_FILES:
        file_path = DATA_DIR / file_name
        fallback_category = file_name.replace("_dataset.json", "").strip().lower()

        if not file_path.exists():
            missing_files.append(file_name)
            print(f"Missing file: {file_name}")
            continue

        print(f"Loading file: {file_name}")
        rows = load_json_file(file_path)

        for index, item in enumerate(rows):
            normalized = normalize_item(item, fallback_category, index, base_date)
            if normalized is None:
                skipped_invalid += 1
                continue

            title_key = normalized["title"].lower()
            if title_key in seen_titles:
                skipped_duplicates += 1
                continue

            Event.objects.create(**normalized)
            seen_titles.add(title_key)
            total_inserted += 1

    print(f"Inserted records: {total_inserted}")
    print(f"Skipped duplicates: {skipped_duplicates}")
    print(f"Skipped invalid records: {skipped_invalid}")
    if missing_files:
        print(f"Missing files count: {len(missing_files)}")
    else:
        print("Missing files count: 0")


if __name__ == "__main__":
    main()
