from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from events.catalog import sync_source
from events.models import CatalogSource
from events.providers import ProviderBlocked


class Command(BaseCommand):
    help = "Run due catalogue jobs. Schedule this command hourly; sources default to disabled and a 24-hour interval."

    def add_arguments(self, parser):
        parser.add_argument("--source", choices=["osm", "ticketmaster"])
        parser.add_argument(
            "--due",
            action="store_true",
            help="Only enabled, due sources (suitable for a host scheduler).",
        )

    def handle(self, *args, **options):
        sources = CatalogSource.objects.all()
        if options["source"]:
            sources = sources.filter(provider=options["source"])
        if options["due"]:
            sources = sources.filter(enabled=True).filter(
                Q(next_sync_at__isnull=True) | Q(next_sync_at__lte=timezone.now())
            )
        if not options["due"] and not options["source"]:
            raise CommandError(
                "Choose --due or --source. No live sources are enabled automatically."
            )
        for source in sources:
            try:
                run = sync_source(source.pk)
                self.stdout.write(
                    f"{source.provider}: {run.status}; received={run.received}; queued={run.queued}. {run.error}"
                )
            except ProviderBlocked as exc:
                self.stdout.write(f"{source.provider}: skipped — {exc}")
