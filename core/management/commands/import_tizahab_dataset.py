import json
import os
from datetime import time

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from events.categories import normalize_category
from events.models import Event

DATASET_DIR = os.path.join(settings.BASE_DIR, "data", "dataset-Tizahab")
DATASET_PATH = os.path.join(DATASET_DIR, "cleaned_dataset.json")
FALLBACK_FIXTURE_PATH = os.path.join(
    settings.BASE_DIR,
    "events",
    "fixtures",
    "riyadh_places.json",
)


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class Command(BaseCommand):
    help = "Import the curated Tizahab dataset into the Event table."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete all existing events before importing.",
        )

    def handle(self, *args, **options):
        # Using cleaned_dataset.json as the single source of truth
        if not os.path.exists(DATASET_PATH):
            self.stdout.write(
                self.style.WARNING(
                    f"Dataset not found: {DATASET_PATH}. Loading bundled fixture."
                )
            )
            call_command("loaddata", FALLBACK_FIXTURE_PATH)
            return

        if options["clear"]:
            deleted, _ = Event.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Cleared {deleted} existing events."))

        with open(DATASET_PATH, encoding="utf-8") as dataset_file:
            records = json.load(dataset_file)

        seen_titles = {
            title.lower() for title in Event.objects.values_list("title", flat=True)
        }
        created_count = 0
        skipped_count = 0
        now = timezone.now()

        for record in records:
            title = (record.get("name") or "").strip()
            if not title or title.lower() in seen_titles:
                skipped_count += 1
                continue

            seen_titles.add(title.lower())
            category = normalize_category(
                record.get("category") or "culture",
                description=record.get("subcategory"),
            )
            location = (
                ", ".join(part for part in [record.get("city"), "Saudi Arabia"] if part)
                or "Riyadh, Saudi Arabia"
            )
            tourism_score = _to_float(record.get("tourism_score")) or 60

            Event.objects.create(
                title=title,
                category=category,
                description=record.get("subcategory") or f"{title} in Riyadh",
                date=now,
                start_date=None,
                end_date=None,
                location=location,
                price=None,
                price_range=record.get("price_level"),
                rating=_to_float(record.get("rating")),
                latitude=_to_float(record.get("latitude")),
                longitude=_to_float(record.get("longitude")),
                start_time=time(9, 0),
                end_time=time(22, 0),
                source="cleaned_dataset.json",
                source_url="",
                is_active=True,
                tourism_relevance=max(1, min(5, round(tourism_score / 20))),
            )
            created_count += 1

        self.stdout.write(self.style.SUCCESS("=== Import complete ==="))
        self.stdout.write(f"  imported : {created_count}")
        self.stdout.write(f"  skipped  : {skipped_count}")
