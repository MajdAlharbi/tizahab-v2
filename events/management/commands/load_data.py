"""
Management command to import events from the curated Tizahab dataset.

Usage:
    python manage.py load_data
    python manage.py load_data --clear
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone

from events.categories import normalize_category
from events.models import Event

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "dataset-Tizahab"
DATASET_FILE = DATA_DIR / "cleaned_dataset.json"


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class Command(BaseCommand):
    help = "Import Riyadh places from cleaned_dataset.json into the Event table."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete all existing events before importing.",
        )

    def handle(self, *args, **options):
        # Using cleaned_dataset.json as the single source of truth
        if not DATASET_FILE.exists():
            self.stderr.write(self.style.ERROR(f"Dataset not found: {DATASET_FILE}"))
            return

        if options["clear"]:
            deleted, _ = Event.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Deleted {deleted} existing events."))

        with DATASET_FILE.open(encoding="utf-8") as dataset_file:
            rows = json.load(dataset_file)

        now = timezone.now()
        rows_read = 0
        created_count = 0
        updated_count = 0
        skipped_count = 0

        self.stdout.write(f"Reading {DATASET_FILE.name}...")

        for row in rows:
            rows_read += 1

            name = (row.get("name") or "").strip()
            if not name:
                skipped_count += 1
                continue

            category = normalize_category(
                row.get("category") or "culture",
                description=row.get("subcategory"),
            )
            description = row.get("subcategory") or "Place in Riyadh"
            location = (
                ", ".join(part for part in [row.get("city"), "Saudi Arabia"] if part)
                or "Riyadh, Saudi Arabia"
            )
            tourism_score = _to_float(row.get("tourism_score")) or 60

            _, created = Event.objects.update_or_create(
                title=name,
                defaults={
                    "category": category,
                    "description": description,
                    "price": None,
                    "price_range": row.get("price_level"),
                    "rating": _to_float(row.get("rating")),
                    "date": now,
                    "start_date": None,
                    "end_date": None,
                    "location": location,
                    "latitude": _to_float(row.get("latitude")),
                    "longitude": _to_float(row.get("longitude")),
                    "source": "cleaned_dataset.json",
                    "source_url": "",
                    "is_active": True,
                    "tourism_relevance": max(1, min(5, round(tourism_score / 20))),
                },
            )

            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Done. "
                f"Rows read: {rows_read}, "
                f"Created: {created_count}, "
                f"Updated: {updated_count}, "
                f"Skipped: {skipped_count}"
            )
        )
