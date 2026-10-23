# Running Tizahab

[Product overview](../README.md) · [API reference](API_DOCUMENTATION.md) ·
[Deployment](DEPLOYMENT.md) · [Contributing](CONTRIBUTING.md)

## Requirements

- Python 3.12 and a dedicated virtual environment.
- SQLite for local development; PostgreSQL for a production database.
- Node.js to run the JavaScript regression tests. Serving the site needs no frontend build.

Tizahab uses Django 5.2, Django REST Framework, Django templates, vanilla JavaScript,
Tailwind CSS and WhiteNoise. The Linux deployment uses Gunicorn and Nginx; Redis
is optional. Dependency ranges and versions are declared in `requirements.txt`.

## Local setup

From the project root on Windows:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Set `DJANGO_SECRET_KEY` in your private `.env` to the generated value. Keep the
development SQLite URL, `DJANGO_DEBUG=True`, and the console email backend. Leave
optional integration credentials blank. Do not overwrite an existing private
environment file. On macOS/Linux use `python3.12 -m venv .venv` and
`source .venv/bin/activate`, then follow the same Python commands.

For a **new development database**:

```powershell
python manage.py migrate
python manage.py runserver
```

Open <http://127.0.0.1:8000/> or <http://127.0.0.1:8000/ar/>. Migrations populate
the bundled place catalog; an additional import command is not required.
Back up and rehearse upgrades before migrating any existing database.

## Administration

Run `python manage.py createsuperuser` against your local development database,
then sign in at `/admin/` or `/admin-panel/`.

- **Super Admin:** an active Django superuser; manages content, users and permissions.
- **Content Manager:** active staff assigned to the `Content Manager` group; reviews
  and publishes content, without user-management privileges. Assign this group to
  new editors explicitly through Django Admin.

Private trips remain accessible only to their owners.

## Checks and tests

The core suite uses isolated databases and synthetic data. Keep Node.js on `PATH`
so its JavaScript regression tests run. Optional Selenium scripts in `tests/`
require separate browser dependencies and an isolated local server.

```powershell
python manage.py check --settings=config.settings_test
python manage.py makemigrations --check --dry-run --settings=config.settings_test
python -m pytest
python -m black --check .
python -m flake8 accounts events daily_plan core config --select=E9,F63,F7,F82
python -m bandit -r accounts events daily_plan core config -ll
python -m pip check
```

Run Bandit with Python 3.12. Do not point test tools at production or personal data.

## Styling and translations

Fonts, icons, brand SVGs and compiled CSS are bundled locally. Shared brand tokens
are in `static/css/design-system.css`. When adding Tailwind utility classes,
rebuild the stylesheet with the existing toolchain:

```powershell
npm exec --cache .verification/npm-cache --yes --package=tailwindcss@3.4.17 -- tailwindcss -i static/css/tailwind-input.css -o static/css/utilities.css --minify
```

Arabic messages live in `locale/ar/LC_MESSAGES/django.po`. After editing them, run
`python manage.py compilemessages` with GNU gettext installed, then
`python scripts/build_ui_messages.py`. Preserve the compiled `.mo` file and RTL styles.

## Catalog and optional integrations

Discovery and planning read the local catalog. Optional provider synchronization
requires deliberate configuration, permitted storage rights and content review.
New records and significant changes enter review; an empty or failed provider
response does not delete published records.

Enable an approved source in Django Admin and set `CATALOG_SYNC_ENABLED` and an
identifying `CATALOG_USER_AGENT`. A host scheduler can run
`python manage.py sync_catalog --due`; no scheduler is installed by the application.
OpenStreetMap/Overpass usage requires attribution and review of ODbL obligations.
Ticketmaster needs credentials, Riyadh coverage and storage approval. Google Places
is not used as a permanent catalog feed. A configured source does not imply a live feed.

The catalog needs ongoing editorial verification. Unknown prices and hours are
displayed explicitly; suggested activity periods are not bookings or guarantees
of opening hours, availability or total spending. Prices apply per place.
Imported names and descriptions retain their source language.

Email uses the console backend locally. SMTP delivery and optional OAuth require
their own credentials and configuration. Notification and privacy controls that
are not implemented are marked unavailable in the interface.

Photo provenance and CC BY / CC BY-SA terms are in
[`credits.json`](../static/images/places/credits.json). Retain those attributions,
the bundled Inter/Noto Sans Arabic OFL files and the Lucide license when distributing assets.
