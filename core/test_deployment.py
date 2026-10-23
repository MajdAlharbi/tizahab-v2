import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

from django.conf import settings
from django.test import SimpleTestCase
import yaml


class ProductionConfigurationTests(SimpleTestCase):
    def run_production(self, script, **overrides):
        environment = {
            **os.environ,
            "DJANGO_SETTINGS_MODULE": "config.settings_production",
            "DJANGO_SECRET_KEY": secrets.token_urlsafe(64),
            "DJANGO_ALLOWED_HOSTS": "portfolio.example,localhost",
            "CSRF_TRUSTED_ORIGINS": "https://portfolio.example",
            "DATABASE_URL": "sqlite:///:memory:",
            "REDIS_URL": "",
            "SENTRY_DSN": "",
            **overrides,
        }
        return subprocess.run(
            [sys.executable, "-B", "-c", "import django; django.setup();\n" + script],
            cwd=settings.BASE_DIR,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )

    def test_proxy_https_avoids_redirect_loop_and_keeps_secure_cookies(self):
        result = self.run_production(
            """
from django.conf import settings
from django.test import Client, override_settings
with override_settings(STORAGES={**settings.STORAGES, 'staticfiles': {'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}}):
    client=Client(enforce_csrf_checks=True)
    plain=client.get('/login/', HTTP_HOST='portfolio.example')
    assert plain.status_code == 301 and plain['Location'] == 'https://portfolio.example/login/'
    proxied=client.get('/login/', HTTP_HOST='portfolio.example', HTTP_X_FORWARDED_PROTO='https')
    assert proxied.status_code == 200
    assert proxied.cookies['csrftoken']['secure']
    assert 'max-age=' in proxied['Strict-Transport-Security']
    assert settings.SESSION_COOKIE_SECURE and settings.CSRF_COOKIE_SECURE
    assert not settings.USE_X_FORWARDED_HOST
    rejected=client.get('/login/', HTTP_HOST='untrusted.example', HTTP_X_FORWARDED_PROTO='https')
    assert rejected.status_code == 400
    response=client.post('/logout/', HTTP_HOST='portfolio.example', HTTP_X_FORWARDED_PROTO='https', HTTP_ORIGIN='https://portfolio.example', HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
    assert response.status_code == 200
"""
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_production_respects_configured_hosts_and_https_origins(self):
        result = self.run_production(
            """
import json
from django.conf import settings
print(json.dumps([settings.ALLOWED_HOSTS, settings.CSRF_TRUSTED_ORIGINS]))
"""
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            [["portfolio.example", "localhost"], ["https://portfolio.example"]],
        )
        invalid = self.run_production(
            "", CSRF_TRUSTED_ORIGINS="http://portfolio.example"
        )
        self.assertNotEqual(invalid.returncode, 0)
        self.assertIn("must use HTTPS", invalid.stderr)
        missing = self.run_production("", DJANGO_ALLOWED_HOSTS="")
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn("DJANGO_ALLOWED_HOSTS", missing.stderr)
        weak = self.run_production(
            "", DJANGO_SECRET_KEY="replace-with-a-generated-local-secret-key"
        )
        self.assertNotEqual(weak.returncode, 0)
        self.assertIn("strong generated production key", weak.stderr)

    def test_database_tls_defaults_secure_and_can_be_disabled_for_private_compose_db(
        self,
    ):
        for value, expected in [("True", "require"), ("False", None)]:
            result = self.run_production(
                """
import json
from django.conf import settings
print(json.dumps(settings.DATABASES['default'].get('OPTIONS', {}).get('sslmode')))
""",
                DATABASE_URL="postgresql://verification@127.0.0.1/unused_synthetic_db",
                DB_SSL_REQUIRE=value,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), expected)

    def test_redis_backend_client_initializes_without_incompatible_options(self):
        result = self.run_production(
            """
from django.core.cache import caches
client=caches['default']._cache.get_client()
assert client.connection_pool.connection_kwargs['host'] == '127.0.0.1'
assert 'CLIENT_CLASS' not in client.connection_pool.connection_kwargs
""",
            REDIS_URL="redis://127.0.0.1:6399/1",
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_production_can_disable_unconfigured_email_without_logging_reset_links(
        self,
    ):
        result = self.run_production(
            """
from django.conf import settings
from django.core.mail import send_mail
assert settings.EMAIL_BACKEND == 'django.core.mail.backends.dummy.EmailBackend'
assert send_mail('Synthetic reset', 'private synthetic reset link', 'noreply@example.invalid', ['visitor@example.test']) == 1
""",
            EMAIL_BACKEND="django.core.mail.backends.dummy.EmailBackend",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_render_blueprint_keeps_demo_resources_free_and_credentials_private(self):
        blueprint = yaml.safe_load(
            (Path(settings.BASE_DIR) / "render.yaml").read_text()
        )
        web, database = blueprint["services"][0], blueprint["databases"][0]
        self.assertEqual(web["plan"], "free")
        self.assertEqual(database["plan"], "free")
        self.assertEqual(web["region"], database["region"])
        self.assertEqual(database["ipAllowList"], [])
        self.assertEqual(web["branch"], "main")
        variables = {entry["key"]: entry for entry in web["envVars"]}
        self.assertEqual(
            variables["DATABASE_URL"]["fromDatabase"]["name"], database["name"]
        )
        self.assertNotIn("value", variables["DATABASE_URL"])
        self.assertIs(variables["DJANGO_SECRET_KEY"]["sync"], False)
        self.assertNotIn("value", variables["DJANGO_SECRET_KEY"])
        self.assertEqual(
            variables["DJANGO_SETTINGS_MODULE"]["value"], "config.settings_production"
        )
        self.assertEqual(variables["CATALOG_SYNC_ENABLED"]["value"], "false")
        self.assertEqual(
            variables["EMAIL_BACKEND"]["value"],
            "django.core.mail.backends.dummy.EmailBackend",
        )

    def test_compose_exposes_only_loopback_proxy_and_requires_database_password(self):
        compose = yaml.safe_load(
            (Path(settings.BASE_DIR) / "docker-compose.yml").read_text()
        )
        services = compose["services"]
        self.assertNotIn("ports", services["db"])
        self.assertNotIn("ports", services["redis"])
        self.assertNotIn("ports", services["web"])
        self.assertEqual(services["nginx"]["ports"], ["127.0.0.1:8080:80"])
        self.assertIn(
            "DB_PASSWORD:?", services["db"]["environment"]["POSTGRES_PASSWORD"]
        )
        self.assertIn("DB_SSL_REQUIRE=False", services["web"]["environment"])
