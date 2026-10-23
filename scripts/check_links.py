#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import io, sys

# Force UTF-8 output on Windows so box-drawing / emoji render correctly
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
"""
check_links.py — URL health checker for Tizahab
================================================
Starts the Django dev server (port 8765), runs all checks, then shuts down.

Checks performed:
  1. Page URLs — each returns the expected HTTP status
  2. Sidebar links — every href in dashboard_base.html resolves
  3. Login redirect — window.location.href points to /home/ not /

Usage:
    python check_links.py
"""

import os
import re
import socket
import subprocess
import sys
import time
from html.parser import HTMLParser
from pathlib import Path

# ── dependency guard ─────────────────────────────────────────────────────────
try:
    import requests
except ImportError:
    sys.exit("ERROR: 'requests' is not installed.  Run: pip install requests")

# ── paths ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent

# Prefer the project's venv; fall back to whichever python ran this script
_WIN_PY = BASE_DIR / ".venv" / "Scripts" / "python.exe"
_UNIX_PY = BASE_DIR / ".venv" / "bin" / "python"
PYTHON = str(
    _WIN_PY if _WIN_PY.exists() else _UNIX_PY if _UNIX_PY.exists() else sys.executable
)

PORT = 8765
BASE_URL = f"http://127.0.0.1:{PORT}"
CONNECT_TIMEOUT = 20  # seconds to wait for the server to start
REQUEST_TIMEOUT = 10  # seconds per HTTP request

# ── colour helpers ────────────────────────────────────────────────────────────
_TTY = sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _TTY else text


green = lambda t: _c("32", t)
red = lambda t: _c("31", t)
yellow = lambda t: _c("33", t)
bold = lambda t: _c("1", t)
dim = lambda t: _c("2", t)

OK = green("✅")
BAD = red("❌")
WARN = yellow("⚠️ ")

# ═════════════════════════════════════════════════════════════════════════════
# 1 · URL manifest
#     (path, human label, expected status code(s))
#     A list means "any of these codes is acceptable."
# ═════════════════════════════════════════════════════════════════════════════
PAGES = [
    # ── Public pages ──────────────────────────────────────────────────────
    ("/", "Landing page", 200),
    ("/login/", "Login page", 200),
    ("/signup/", "Signup page", 200),
    ("/api/auth/ui/forgot-password/", "Forgot password page", 200),
    ("/api/auth/ui/preferences/", "Preferences / onboarding", 200),
    # ── Authenticated dashboard pages ──────────────────────────────────
    ("/home/", "Dashboard home", 200),
    ("/dashboard/", "Dashboard alias", 200),
    ("/events/page/", "Events list", 200),
    ("/daily-plan/", "Daily plan", 200),
    ("/map/", "Map page", 200),
    ("/profile/", "Profile page", 200),
    ("/settings/", "Settings page", 200),
    ("/admin-panel/", "Admin panel", 200),
    # ── Route that does NOT exist yet ──────────────────────────────────
    ("/onboarding/", "Onboarding (not yet wired)", [200, 404]),
    # ── API endpoints (no token → 401 is acceptable) ───────────────────
    ("/api/events/", "Events API", [200, 401]),
    ("/api/daily-plan/", "Daily plan API", [200, 401]),
    ("/api/auth/login/", "Auth login API", [200, 405]),  # GET on POST-only view
]

# ═════════════════════════════════════════════════════════════════════════════
# 2 · Sidebar link manifest
# ═════════════════════════════════════════════════════════════════════════════
SIDEBAR_TEMPLATE = BASE_DIR / "templates" / "dashboard_base.html"

# ═════════════════════════════════════════════════════════════════════════════
# 3 · Login redirect check
# ═════════════════════════════════════════════════════════════════════════════
LOGIN_TEMPLATE = BASE_DIR / "templates" / "login.html"
EXPECTED_LOGIN_REDIRECT = "/home/"


# ─────────────────────────────────────────────────────────────────────────────
# Dev-server helpers
# ─────────────────────────────────────────────────────────────────────────────


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.2)
        return s.connect_ex(("127.0.0.1", port)) == 0


def start_server() -> subprocess.Popen | None:
    """Spawn `manage.py runserver`; return the Popen object, or None if the
    port was already in use (meaning an external server is handling it)."""
    if _port_open(PORT):
        print(f"  {WARN} Port {PORT} already open — using the existing server.\n")
        return None

    proc = subprocess.Popen(
        [PYTHON, "manage.py", "runserver", f"127.0.0.1:{PORT}", "--noreload"],
        cwd=BASE_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print(f"  Starting Django dev server on port {PORT}", end="", flush=True)
    deadline = time.time() + CONNECT_TIMEOUT
    while time.time() < deadline:
        if _port_open(PORT):
            print(f" {green('ready')}\n")
            return proc
        print(".", end="", flush=True)
        time.sleep(0.3)

    proc.terminate()
    sys.exit(red(f"\n  ERROR: Server did not start within {CONNECT_TIMEOUT}s"))


def stop_server(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


# ─────────────────────────────────────────────────────────────────────────────
# HTML parser — extract <a href="..."> values
# ─────────────────────────────────────────────────────────────────────────────


class _HrefCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            for name, val in attrs:
                if name == "href" and val:
                    self.hrefs.append(val)


def _internal_hrefs(path: Path) -> list[str]:
    """Return deduplicated internal absolute paths from all <a> tags in `path`."""
    parser = _HrefCollector()
    parser.feed(path.read_text(encoding="utf-8"))
    seen, result = set(), []
    for href in parser.hrefs:
        href = href.strip()
        if (
            href.startswith("/")  # absolute path
            and "{{" not in href  # not a Django template expression
            and "{%" not in href
            and href != "#"
            and href not in seen
        ):
            seen.add(href)
            result.append(href)
    return sorted(result)


# ─────────────────────────────────────────────────────────────────────────────
# Login-redirect extractor
# ─────────────────────────────────────────────────────────────────────────────


def _login_redirect(path: Path) -> str | None:
    """Return the redirect URL that follows localStorage.setItem("access", ...)
    in the login template's success path."""
    text = path.read_text(encoding="utf-8")
    # Match window.location.href that comes after the token is stored
    m = re.search(
        r'localStorage\.setItem\(["\']access["\'].*?'
        r'window\.location\.href\s*=\s*["\']([^"\']+)["\']',
        text,
        re.DOTALL,
    )
    return m.group(1) if m else None


# ─────────────────────────────────────────────────────────────────────────────
# Single URL checker
# ─────────────────────────────────────────────────────────────────────────────


def check(path: str, label: str, expected) -> tuple[bool, str]:
    """Return (passed, formatted_line)."""
    url = BASE_URL + path
    codes = [expected] if isinstance(expected, int) else list(expected)

    try:
        r = requests.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        status = r.status_code
    except requests.ConnectionError:
        return False, f"{BAD}  {path:<44} {dim(label)} — {red('connection refused')}"
    except requests.Timeout:
        return False, f"{BAD}  {path:<44} {dim(label)} — {red('timed out')}"
    except Exception as exc:
        return False, f"{BAD}  {path:<44} {dim(label)} — {red(str(exc))}"

    ok = status in codes
    status_str = green(str(status)) if ok else red(str(status))
    exp_str = " or ".join(str(c) for c in codes)
    suffix = "" if ok else f"  {dim(f'(expected {exp_str})')}"
    icon = OK if ok else BAD
    return ok, f"{icon}  {path:<44} {dim(label)} — HTTP {status_str}{suffix}"


# ─────────────────────────────────────────────────────────────────────────────
# Section header printer
# ─────────────────────────────────────────────────────────────────────────────


def _section(title: str) -> None:
    print(bold(f"\n  ── {title} {'─' * max(0, 54 - len(title))}"))


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    print()
    print(bold("  ══════════════════════════════════════════════════════"))
    print(bold("    Tizahab · Link Checker"))
    print(bold("  ══════════════════════════════════════════════════════"))
    print()

    results: list[tuple[bool, str]] = []

    # ── Start server ─────────────────────────────────────────────────────────
    server = start_server()

    # ── Section 1 · URL status ────────────────────────────────────────────
    _section("Page & API URL status")
    for path, label, expected in PAGES:
        ok, line = check(path, label, expected)
        results.append((ok, line))
        print(f"  {line}")

    # ── Section 2 · Sidebar links ─────────────────────────────────────────
    _section(f"Sidebar links  ({SIDEBAR_TEMPLATE.name})")
    if not SIDEBAR_TEMPLATE.exists():
        line = f"{BAD}  {SIDEBAR_TEMPLATE} — file not found"
        results.append((False, line))
        print(f"  {line}")
    else:
        hrefs = _internal_hrefs(SIDEBAR_TEMPLATE)
        print(f"  {dim(f'Found {len(hrefs)} unique internal links')}\n")
        for href in hrefs:
            # 405 is acceptable for /logout/ — Django LogoutView is POST-only
            ok, line = check(href, f"sidebar href", [200, 301, 302, 405])
            results.append((ok, line))
            print(f"  {line}")

    # ── Section 3 · Login redirect ────────────────────────────────────────
    _section(f"Login JS redirect  ({LOGIN_TEMPLATE.name})")
    if not LOGIN_TEMPLATE.exists():
        line = f"{BAD}  {LOGIN_TEMPLATE} — file not found"
        results.append((False, line))
        print(f"  {line}")
    else:
        redirect = _login_redirect(LOGIN_TEMPLATE)
        if redirect is None:
            line = f"{WARN}  Could not find window.location.href after token storage"
            results.append((False, line))
            print(f"  {line}")
        elif redirect == EXPECTED_LOGIN_REDIRECT:
            line = f"{OK}  window.location.href = {green(repr(redirect))}  {dim('(correct)')}"
            results.append((True, line))
            print(f"  {line}")
        else:
            line = (
                f"{BAD}  window.location.href = {red(repr(redirect))}"
                f"  {dim(f'— expected {EXPECTED_LOGIN_REDIRECT!r}')}"
            )
            results.append((False, line))
            print(f"  {line}")

    # ── Summary ───────────────────────────────────────────────────────────
    total = len(results)
    passed = sum(1 for ok, _ in results if ok)
    failed = total - passed

    print()
    print(bold("  ══════════════════════════════════════════════════════"))
    if failed == 0:
        print(f"  {green(f'All {total} checks passed')}  {OK}")
    else:
        print(
            f"  {green(f'{passed} passed')}   {red(f'{failed} failed')}   {dim(f'({total} total)')}"
        )
        print()
        print(bold("  Failed checks:"))
        for ok, line in results:
            if not ok:
                print(f"  {line}")
    print(bold("  ══════════════════════════════════════════════════════"))
    print()

    # ── Cleanup ───────────────────────────────────────────────────────────
    stop_server(server)
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
