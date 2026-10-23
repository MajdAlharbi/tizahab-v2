#!/bin/bash
set -e

python manage.py migrate --noinput
python manage.py collectstatic --noinput

# Seed event data when the database is empty. This keeps production deploys
# deterministic even on a brand-new database.
if [ "${DJANGO_LOAD_INITIAL_DATA:-True}" = "True" ]; then
  EVENT_COUNT=$(python manage.py shell -c "from events.models import Event; print(Event.objects.count())")
  if [ "$EVENT_COUNT" = "0" ]; then
    echo "No events found - importing curated Tizahab dataset or bundled fixture..."
    python manage.py import_tizahab_dataset
    EVENT_COUNT=$(python manage.py shell -c "from events.models import Event; print(Event.objects.count())")
    echo "Initial data load complete ($EVENT_COUNT events)."
  else
    echo "Events already present ($EVENT_COUNT rows) - skipping initial data load."
  fi
else
  echo "Initial data auto-seeding disabled."
fi

GUNICORN_WORKERS="${GUNICORN_WORKERS:-2}"

exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "$GUNICORN_WORKERS"
