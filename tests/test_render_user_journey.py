"""
Optional local Selenium smoke checks. Use an isolated database and synthetic data.
These historical scripts are separate from the core release test suite.

Run:
    python tests/test_render_user_journey.py
    python tests/test_render_user_journey.py --headless
    python tests/test_render_user_journey.py --url http://127.0.0.1:8000
    python tests/test_render_user_journey.py --slow

Dependencies:
    pip install selenium webdriver-manager requests
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, parse_qs


MISSING_DEPS: list[str] = []

try:
    import requests
except ImportError:
    MISSING_DEPS.append("requests")

try:
    from selenium import webdriver
    from selenium.common.exceptions import (
        ElementClickInterceptedException,
        JavascriptException,
        NoSuchElementException,
        TimeoutException,
        WebDriverException,
    )
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.remote.webelement import WebElement
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
except ImportError:
    MISSING_DEPS.append("selenium")

try:
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:
    MISSING_DEPS.append("webdriver-manager")


DEFAULT_URL = "http://127.0.0.1:8000"
ARTIFACT_DIR = Path(__file__).resolve().parent / "e2e_artifacts"
JSON_REPORT = ARTIFACT_DIR / "render_e2e_report.json"
TEXT_REPORT = ARTIFACT_DIR / "render_e2e_report.txt"


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str
    section: str = "positive path"
    url: str = ""
    screenshot: str = ""
    console_errors: list[str] | None = None


class RenderJourneyTester:
    def __init__(
        self, base_url: str, headless: bool = False, slow: bool = False
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.headless = headless
        self.slow = slow
        self.results: list[CheckResult] = []
        self.session = requests.Session()
        self.driver: webdriver.Chrome | None = None
        self.wait: WebDriverWait | None = None
        self.test_email = f"tizahab_e2e_{int(time.time())}@example.com"
        self.test_password = "TizahabE2E123!"
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    def build_driver(self) -> bool:
        opts = Options()
        if self.headless:
            opts.add_argument("--headless=new")
        opts.add_argument("--window-size=1440,1000")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--disable-extensions")
        opts.add_argument("--log-level=3")
        opts.set_capability("goog:loggingPrefs", {"browser": "ALL"})

        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=opts)
            self.wait = WebDriverWait(self.driver, 15)
            return True
        except Exception as exc:
            self.fail(
                "browser startup",
                "Chrome/WebDriver could not start. Exact blocker: "
                f"{type(exc).__name__}: {exc}",
            )
            return False

    def close(self) -> None:
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass

    def full_url(self, path: str) -> str:
        return urljoin(self.base_url + "/", path.lstrip("/"))

    def add_result(
        self,
        status: str,
        name: str,
        detail: str,
        section: str = "",
        url: str = "",
        screenshot: str = "",
        console_errors: list[str] | None = None,
    ) -> None:
        result = CheckResult(
            name=name,
            status=status,
            detail=detail,
            section=section or self.section_for(name),
            url=url or self.current_url(),
            screenshot=screenshot,
            console_errors=console_errors or [],
        )
        self.results.append(result)
        icon = {"PASS": "PASS", "WARN": "WARN", "FAIL": "FAIL"}[status]
        line = f"[{icon}] {name}: {detail}"
        try:
            print(line)
        except UnicodeEncodeError:
            print(line.encode("ascii", errors="replace").decode("ascii"))

    def section_for(self, name: str) -> str:
        lowered = name.lower()
        if (
            "negative" in lowered
            or "validation" in lowered
            or "empty form" in lowered
            or "invalid" in lowered
        ):
            return "negative validation"
        if "button audit" in lowered:
            return "button audit"
        if "api category" in lowered:
            return "api category validation"
        if "console" in lowered:
            return "console errors"
        return "positive path"

    def pass_(self, name: str, detail: str, url: str = "", section: str = "") -> None:
        self.add_result("PASS", name, detail, section=section, url=url)

    def warn(self, name: str, detail: str, url: str = "", section: str = "") -> None:
        self.add_result("WARN", name, detail, section=section, url=url)

    def fail(self, name: str, detail: str, url: str = "", section: str = "") -> None:
        screenshot = self.screenshot(name) if self.driver else ""
        errors = self.console_errors() if self.driver else []
        self.add_result(
            "FAIL",
            name,
            detail,
            section=section,
            url=url,
            screenshot=screenshot,
            console_errors=errors,
        )

    def current_url(self) -> str:
        try:
            return self.driver.current_url if self.driver else ""
        except Exception:
            return ""

    def screenshot(self, name: str) -> str:
        if not self.driver:
            return ""
        safe = "".join(ch if ch.isalnum() else "_" for ch in name.lower()).strip("_")
        path = ARTIFACT_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe}.png"
        try:
            self.driver.save_screenshot(str(path))
            return str(path)
        except WebDriverException:
            return ""

    def pause(self, seconds: float = 0.25) -> None:
        if self.slow:
            time.sleep(max(seconds, 0.8))

    def goto(self, path: str) -> None:
        assert self.driver is not None
        self.driver.get(self.full_url(path))
        self.pause()

    def find(self, by: str, selector: str, timeout: int = 8) -> WebElement | None:
        if not self.wait:
            return None
        try:
            return WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, selector))
            )
        except TimeoutException:
            return None

    def visible(self, by: str, selector: str, timeout: int = 8) -> WebElement | None:
        if not self.driver:
            return None
        try:
            return WebDriverWait(self.driver, timeout).until(
                EC.visibility_of_element_located((by, selector))
            )
        except TimeoutException:
            return None

    def all(self, by: str, selector: str) -> list[WebElement]:
        if not self.driver:
            return []
        try:
            return self.driver.find_elements(by, selector)
        except WebDriverException:
            return []

    def click(self, el: WebElement) -> bool:
        if not self.driver:
            return False
        try:
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", el
            )
            WebDriverWait(self.driver, 5).until(lambda _d: el.is_enabled())
            el.click()
            self.pause()
            return True
        except (ElementClickInterceptedException, WebDriverException):
            try:
                self.driver.execute_script("arguments[0].click();", el)
                self.pause()
                return True
            except (JavascriptException, WebDriverException):
                return False

    def wait_url_contains(self, fragment: str, timeout: int = 10) -> bool:
        if not self.driver:
            return False
        try:
            WebDriverWait(self.driver, timeout).until(EC.url_contains(fragment))
            return True
        except TimeoutException:
            return False

    def wait_document_ready(self, timeout: int = 10) -> bool:
        if not self.driver:
            return False
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            return True
        except TimeoutException:
            return False

    def console_errors(self) -> list[str]:
        if not self.driver:
            return []
        ignored = (
            "favicon.ico",
            "chrome-extension://",
            "ResizeObserver loop",
            "/api/auth/me/ - Failed to load resource: the server responded with a status of 401",
            "/api/auth/session-token/ - Failed to load resource: the server responded with a status of 403",
            "/api/auth/admin/users/ - Failed to load resource: the server responded with a status of 401",
            "/api/auth/admin/users/ - Failed to load resource: the server responded with a status of 403",
            "/api/auth/signup/ - Failed to load resource: the server responded with a status of 400",
            "/api/auth/login/ - Failed to load resource: the server responded with a status of 400",
        )
        try:
            logs = self.driver.get_log("browser")
        except (ValueError, WebDriverException):
            return []
        errors = []
        for entry in logs:
            message = str(entry.get("message", ""))
            if entry.get("level") != "SEVERE":
                continue
            if any(part in message for part in ignored):
                continue
            errors.append(message[:500])
        return errors

    def clear_console_logs(self) -> None:
        if not self.driver:
            return
        try:
            self.driver.get_log("browser")
        except (ValueError, WebDriverException):
            pass

    def check_console(self, context: str) -> None:
        errors = self.console_errors()
        if errors:
            self.fail(
                f"console errors - {context}",
                f"{len(errors)} severe console error(s): {errors[0][:180]}",
            )
        else:
            self.pass_(
                f"console errors - {context}", "No severe browser console errors"
            )

    def assert_no_500(self, context: str) -> bool:
        text = self.body_text().lower()
        title = ""
        try:
            title = (self.driver.title or "").lower() if self.driver else ""
        except WebDriverException:
            title = ""
        bad = (
            "server error" in text
            or "traceback" in text
            or "500" in title
            or "internal server error" in text
        )
        if bad:
            self.fail(f"{context} no 500", "Page appears to be a server error page")
            return False
        self.pass_(f"{context} no 500", "No 500/server-error page detected")
        return True

    def assert_not_api_browsable_page(self, context: str) -> bool:
        current = self.current_url()
        text = self.body_text()
        is_api = "/api/" in urlparse(current).path and (
            "Django REST framework" in text
            or "HTTP 405" in text
            or 'Method "GET" not allowed' in text
        )
        if is_api:
            self.fail(
                f"{context} not DRF API", f"Navigated to browsable API page: {current}"
            )
            return False
        self.pass_(f"{context} not DRF API", "Not on DRF browsable API")
        return True

    def assert_current_url_not_api_auth(self, context: str) -> bool:
        current = self.current_url()
        if "/api/auth/login/" in current or "/api/auth/signup/" in current:
            self.fail(f"{context} not api auth", f"Unexpected auth API URL: {current}")
            return False
        self.pass_(f"{context} not api auth", "Did not navigate to auth API endpoint")
        return True

    def assert_visible_error_or_validation(self, context: str) -> bool:
        if not self.driver:
            return False
        visible_text = self.wait_for_validation_text(timeout=8)
        if visible_text:
            self.pass_(
                f"{context} validation", f"Visible validation: {visible_text[:160]}"
            )
            return True
        invalid_count = self.invalid_field_count()
        if invalid_count:
            self.pass_(
                f"{context} validation",
                f"Browser field validation active on {invalid_count} field(s)",
            )
            return True
        self.fail(
            f"{context} validation",
            "No visible error message or invalid field state found",
        )
        return False

    def wait_for_validation_text(self, timeout: int = 8) -> str:
        if not self.driver:
            return ""
        selectors = [
            "[role='alert']:not(.hidden)",
            "#signup-error:not(.hidden)",
            "#login-error:not(.hidden)",
            "#confirm-mismatch:not(.hidden)",
            "[id$='-error']:not(.hidden)",
            "#pref-message:not(.hidden)",
        ]

        def find_text(_driver: webdriver.Chrome) -> str:
            for selector in selectors:
                elements = self.all(By.CSS_SELECTOR, selector)
                visible_text = [
                    el.text.strip()
                    for el in elements
                    if el.is_displayed() and el.text.strip()
                ]
                if visible_text:
                    return visible_text[0]
            return ""

        try:
            return WebDriverWait(self.driver, timeout).until(find_text)
        except TimeoutException:
            return ""

    def invalid_field_count(self) -> int:
        if not self.driver:
            return 0
        try:
            return int(
                self.driver.execute_script(
                    "return Array.from(document.querySelectorAll('input,select,textarea')).filter(el => !el.checkValidity()).length;"
                )
            )
        except (JavascriptException, WebDriverException, TypeError, ValueError):
            return 0

    def safe_click_button(
        self, element: WebElement, context: str, restore_url: str | None = None
    ) -> bool:
        before = self.current_url()
        clicked = self.click(element)
        if not clicked:
            self.warn(f"{context} safe click", "Element could not be clicked")
            return False
        self.pause(0.4)
        self.assert_no_500(context)
        self.assert_not_api_browsable_page(context)
        self.check_console(context)
        if restore_url and self.current_url() != before:
            self.goto(restore_url)
            self.wait_document_ready()
        return True

    def open_external_link_safely(self, link: WebElement, context: str) -> None:
        if not self.driver:
            return
        href = link.get_attribute("href") or ""
        if not href:
            self.warn(f"{context} external link", "External link has no href")
            return
        original = self.driver.current_window_handle
        handles_before = set(self.driver.window_handles)
        try:
            self.driver.execute_script(
                "window.open(arguments[0], '_blank', 'noopener,noreferrer');", href
            )
            WebDriverWait(self.driver, 5).until(
                lambda d: len(set(d.window_handles) - handles_before) >= 1
            )
            new_handle = list(set(self.driver.window_handles) - handles_before)[0]
            self.driver.switch_to.window(new_handle)
            self.pass_(
                f"{context} external link",
                f"Opened external href in temporary tab: {urlparse(href).netloc}",
            )
            self.driver.close()
            self.driver.switch_to.window(original)
        except Exception as exc:
            try:
                self.driver.switch_to.window(original)
            except Exception:
                pass
            self.warn(
                f"{context} external link",
                f"Could not open external href safely: {type(exc).__name__}: {exc}",
            )

    def request(
        self, path: str, allow_redirects: bool = True
    ) -> requests.Response | None:
        url = self.full_url(path)
        last_exc: requests.RequestException | None = None
        for attempt in range(2):
            try:
                response = self.session.get(
                    url, timeout=25, allow_redirects=allow_redirects
                )
                if attempt == 1:
                    self.warn(
                        f"request {path} retry",
                        "Initial safe GET timed out/failed once, retry succeeded",
                        url=response.url,
                    )
                return response
            except (requests.Timeout, requests.exceptions.ReadTimeout) as exc:
                last_exc = exc
                if attempt == 0:
                    continue
            except requests.RequestException as exc:
                last_exc = exc
                break
        self.fail(
            f"request {path}",
            f"Request failed: {type(last_exc).__name__}: {last_exc}",
            url=url,
        )
        return None

    def run(self) -> None:
        self.check_public_routes()
        self.check_protected_redirects()
        self.check_api_events()

        browser_ok = self.build_driver()
        if browser_ok:
            try:
                self.browser_public_smoke()
                self.auth_tab_navigation()
                self.negative_auth_forms()
                self.signup_flow()
                self.signup_duplicate_email_negative()
                self.onboarding_flow()
                self.explore_flow()
                self.add_to_plan_flow()
                self.daily_plan_flow()
                self.optional_pages_flow()
                self.profile_settings_flow()
                self.button_audit_flow()
                self.logout_flow()
            except Exception as exc:
                self.fail(
                    "unexpected e2e exception",
                    f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=5)}",
                )
            finally:
                self.close()

        self.write_reports()
        self.print_summary()

    def check_public_routes(self) -> None:
        for path in ["/", "/login/", "/signup/", "/events/page/", "/api/events/"]:
            response = self.request(path)
            if response is None:
                continue
            content_type = response.headers.get("content-type", "")
            if response.status_code == 200:
                self.pass_(
                    f"public route {path}", f"200 OK ({content_type})", url=response.url
                )
            else:
                self.fail(
                    f"public route {path}",
                    f"Expected 200, got {response.status_code}",
                    url=response.url,
                )

    def check_protected_redirects(self) -> None:
        expected = {
            "/onboarding/": "/onboarding/",
            "/daily-plan/": "/daily-plan/",
            "/profile/": "/profile/",
        }
        for path, next_value in expected.items():
            response = self.request(path, allow_redirects=False)
            if response is None:
                continue
            location = response.headers.get("location", "")
            parsed = urlparse(location)
            qs = parse_qs(parsed.query)
            if response.status_code in (
                301,
                302,
                303,
                307,
                308,
            ) and parsed.path.endswith("/login/"):
                actual_next = (qs.get("next") or [""])[0]
                if actual_next == next_value:
                    self.pass_(
                        f"protected redirect {path}",
                        f"Redirects to login with next={actual_next}",
                    )
                else:
                    self.warn(
                        f"protected redirect {path}",
                        f"Redirects to login but next was {actual_next!r}; expected {next_value!r}",
                    )
            elif response.status_code == 200:
                self.fail(
                    f"protected redirect {path}", "Route returned 200 while logged out"
                )
            else:
                self.fail(
                    f"protected redirect {path}",
                    f"Expected login redirect, got {response.status_code}",
                )

    def check_api_events(self) -> None:
        response = self.request("/api/events/")
        if response is None:
            return
        if response.status_code != 200:
            self.fail(
                "api events status",
                f"Expected 200, got {response.status_code}",
                url=response.url,
            )
            return
        try:
            data = response.json()
        except ValueError as exc:
            self.fail("api events json", f"Invalid JSON: {exc}", url=response.url)
            return
        results = data.get("results") if isinstance(data, dict) else None
        count = data.get("count") if isinstance(data, dict) else None
        if (
            isinstance(count, int)
            and count > 0
            and isinstance(results, list)
            and results
        ):
            self.pass_(
                "api events data",
                f"count={count}, results={len(results)}",
                url=response.url,
            )
        else:
            self.fail(
                "api events data",
                f"Expected count/results > 0, got count={count}, results={len(results or [])}",
                url=response.url,
            )
            return
        first = results[0]
        required = ["id", "title", "category"]
        optional = ["latitude", "longitude", "rating"]
        missing = [key for key in required if first.get(key) in (None, "")]
        available_optional = [
            key for key in optional if first.get(key) not in (None, "")
        ]
        if missing:
            self.fail(
                "api events first result fields", f"Missing required fields: {missing}"
            )
        else:
            self.pass_(
                "api events first result fields",
                f"Required fields present; optional present: {available_optional or 'none'}",
            )
        self.check_api_category_filters()

    def check_api_category_filters(self) -> None:
        for category in ["food", "culture", "nature", "heritage", "events"]:
            response = self.request(f"/api/events/?category={category}")
            if response is None:
                continue
            if response.status_code != 200:
                self.fail(
                    f"api category {category}",
                    f"Expected 200, got {response.status_code}",
                    url=response.url,
                )
                continue
            try:
                data = response.json()
            except ValueError as exc:
                self.fail(
                    f"api category {category}", f"Invalid JSON: {exc}", url=response.url
                )
                continue
            results = data.get("results") if isinstance(data, dict) else data
            if not isinstance(results, list) or not results:
                count = data.get("count") if isinstance(data, dict) else 0
                if count == 0:
                    self.warn(
                        f"api category {category}",
                        "API category has zero results; acceptable if UI has clear empty state",
                        url=response.url,
                    )
                else:
                    self.fail(
                        f"api category {category}",
                        "Expected results list when count is nonzero",
                        url=response.url,
                    )
                continue
            bad = [
                item.get("category")
                for item in results
                if item.get("category") != category
            ]
            if bad:
                self.fail(
                    f"api category {category}",
                    f"Unexpected categories returned: {bad[:5]}",
                    url=response.url,
                )
            else:
                self.pass_(
                    f"api category {category}",
                    f"{len(results)} result(s), all category={category}",
                    url=response.url,
                )

    def browser_public_smoke(self) -> None:
        for path in ["/", "/login/", "/signup/", "/events/page/"]:
            self.goto(path)
            self.wait_document_ready()
            if self.driver and self.driver.title:
                self.pass_(f"browser page {path}", f"Loaded title: {self.driver.title}")
            else:
                self.fail(f"browser page {path}", "Page loaded without title")
            self.check_console(path)

    def auth_tab_navigation(self) -> None:
        self.goto("/signup/")
        login_tab = self.visible(By.XPATH, "//a[normalize-space()='Login']", 8)
        if not login_tab or not self.click(login_tab):
            self.fail("signup login tab", "Could not click Login tab on signup page")
        elif (
            "/login/" in self.current_url()
            and "/api/auth/login/" not in self.current_url()
        ):
            if self.visible(By.ID, "login-btn", 8):
                self.pass_(
                    "signup login tab",
                    "Login tab navigates to /login/ and shows login form",
                )
            else:
                self.fail(
                    "signup login tab",
                    "Navigated to /login/ but login form was not visible",
                )
        else:
            self.fail(
                "signup login tab", f"Unexpected target URL: {self.current_url()}"
            )
        self.assert_current_url_not_api_auth("signup login tab")
        self.assert_not_api_browsable_page("signup login tab")

        self.goto("/login/")
        signup_tab = self.visible(
            By.XPATH, "//a[normalize-space()='Create Account']", 8
        )
        if not signup_tab or not self.click(signup_tab):
            self.fail(
                "login create account tab",
                "Could not click Create Account tab on login page",
            )
        elif (
            "/signup/" in self.current_url()
            and "/api/auth/signup/" not in self.current_url()
        ):
            if self.visible(By.ID, "signup-form", 8):
                self.pass_(
                    "login create account tab",
                    "Create Account tab navigates to /signup/ and shows signup form",
                )
            else:
                self.fail(
                    "login create account tab",
                    "Navigated to /signup/ but signup form was not visible",
                )
        else:
            self.fail(
                "login create account tab",
                f"Unexpected target URL: {self.current_url()}",
            )
        self.assert_current_url_not_api_auth("login create account tab")
        self.assert_not_api_browsable_page("login create account tab")

    def negative_auth_forms(self) -> None:
        self.signup_negative_empty()
        self.signup_negative_invalid_email()
        self.signup_negative_short_password()
        self.signup_negative_mismatch()
        self.login_negative_empty()
        self.login_negative_invalid_email()
        self.login_negative_unknown_email()
        self.login_negative_wrong_password_like_test_email()

    def submit_signup_negative(self, name: str, values: dict[str, str]) -> None:
        self.goto("/signup/")
        self.clear_console_logs()
        form = self.visible(By.ID, "signup-form", 8)
        if not form:
            self.fail(name, "Signup form missing")
            return
        for element_id, value in values.items():
            el = self.find(By.ID, element_id, 4)
            if el:
                el.clear()
                if value:
                    el.send_keys(value)
        btn = self.visible(By.ID, "signup-btn", 4)
        if btn:
            self.click(btn)
        self.pause(0.5)
        if "/signup/" in self.current_url():
            self.pass_(name, "Stayed on signup page after invalid input")
        else:
            self.fail(
                name,
                f"Unexpected navigation after invalid signup: {self.current_url()}",
            )
        self.assert_visible_error_or_validation(name)
        self.assert_no_500(name)
        self.assert_current_url_not_api_auth(name)
        self.assert_not_api_browsable_page(name)
        self.check_console(name)

    def signup_negative_empty(self) -> None:
        self.submit_signup_negative("signup negative empty form", {})

    def signup_negative_invalid_email(self) -> None:
        self.submit_signup_negative(
            "signup negative invalid email",
            {
                "signup-name": "Bad Email",
                "signup-email": "not-an-email",
                "signup-password": self.test_password,
                "signup-confirm": self.test_password,
            },
        )

    def signup_negative_short_password(self) -> None:
        self.submit_signup_negative(
            "signup negative short password",
            {
                "signup-name": "Short Password",
                "signup-email": f"short_{int(time.time())}@example.com",
                "signup-password": "123",
                "signup-confirm": "123",
            },
        )

    def signup_negative_mismatch(self) -> None:
        self.submit_signup_negative(
            "signup negative password mismatch",
            {
                "signup-name": "Mismatch Password",
                "signup-email": f"mismatch_{int(time.time())}@example.com",
                "signup-password": self.test_password,
                "signup-confirm": "Different123!",
            },
        )

    def submit_login_negative(
        self, name: str, email: str = "", password: str = ""
    ) -> None:
        self.goto("/login/")
        self.clear_console_logs()
        email_el = self.find(By.CSS_SELECTOR, "input[name='email']", 6)
        password_el = self.find(By.CSS_SELECTOR, "input[name='password']", 6)
        if email_el:
            email_el.clear()
            if email:
                email_el.send_keys(email)
        if password_el:
            password_el.clear()
            if password:
                password_el.send_keys(password)
        btn = self.visible(By.ID, "login-btn", 4)
        if btn:
            self.click(btn)
        self.pause(0.6)
        if "/login/" in self.current_url():
            self.pass_(name, "Stayed on login page after invalid input")
        else:
            self.fail(
                name, f"Unexpected navigation after invalid login: {self.current_url()}"
            )
        self.assert_visible_error_or_validation(name)
        self.assert_no_500(name)
        self.assert_current_url_not_api_auth(name)
        self.assert_not_api_browsable_page(name)
        self.check_console(name)

    def login_negative_empty(self) -> None:
        self.submit_login_negative("login negative empty form")

    def login_negative_invalid_email(self) -> None:
        self.submit_login_negative(
            "login negative invalid email", "not-an-email", "whatever"
        )

    def login_negative_unknown_email(self) -> None:
        self.submit_login_negative(
            "login negative unknown email",
            f"unknown_{int(time.time())}@example.com",
            "WrongPass123!",
        )

    def login_negative_wrong_password_like_test_email(self) -> None:
        self.submit_login_negative(
            "login negative wrong password", self.test_email, "WrongPass123!"
        )

    def signup_flow(self) -> None:
        self.goto("/signup/")
        self.clear_console_logs()
        form = self.visible(By.ID, "signup-form", 10)
        if not form:
            self.fail("signup form", "Signup form #signup-form did not render")
            return

        fields = {
            "signup-name": "Tizahab E2E User",
            "signup-email": self.test_email,
            "signup-password": self.test_password,
            "signup-confirm": self.test_password,
        }
        try:
            for element_id, value in fields.items():
                el = self.visible(By.ID, element_id, 8)
                if not el:
                    self.fail("signup form fields", f"Missing #{element_id}")
                    return
                el.clear()
                el.send_keys(value)
            self.pass_("signup form fill", f"Filled unique email {self.test_email}")
        except WebDriverException as exc:
            self.fail("signup form fill", f"Could not fill signup form: {exc}")
            return

        btn = self.visible(By.ID, "signup-btn", 8)
        if not btn or not self.click(btn):
            self.fail("signup submit", "Could not click signup submit button")
            return

        success = (
            self.wait_url_contains("/onboarding/", 18)
            or self.wait_url_contains("/home/", 2)
            or self.wait_url_contains("/daily-plan/", 2)
        )
        if success:
            self.pass_(
                "signup submit", f"Signup succeeded; current URL {self.current_url()}"
            )
        else:
            error = self.visible(By.ID, "signup-error", 2)
            detail = (
                error.text.strip()
                if error and error.is_displayed()
                else f"Unexpected URL {self.current_url()}"
            )
            self.fail("signup submit", detail)
        self.check_console("signup")

    def signup_duplicate_email_negative(self) -> None:
        self.goto("/signup/")
        if "/signup/" not in self.current_url():
            self.warn(
                "signup negative duplicate email",
                f"Could not load signup page after valid signup; current URL {self.current_url()}",
            )
            return
        self.submit_signup_negative(
            "signup negative duplicate email",
            {
                "signup-name": "Duplicate E2E User",
                "signup-email": self.test_email,
                "signup-password": self.test_password,
                "signup-confirm": self.test_password,
            },
        )

    def onboarding_flow(self) -> None:
        self.goto("/onboarding/")
        if "/login/" in self.current_url():
            self.fail(
                "onboarding access after signup",
                f"Redirected to login: {self.current_url()}",
            )
            return

        self.click_by_id("next-1", "onboarding negative no interests continue")
        self.assert_visible_error_or_validation("onboarding negative no interests")
        self.assert_no_500("onboarding negative no interests")
        if "/login/" in self.current_url():
            self.fail(
                "onboarding negative no interests auth",
                "User was logged out during validation",
            )
            return
        self.check_console("onboarding negative no interests")

        selected = 0
        for category in ["culture", "heritage", "nature", "events"]:
            card = self.find(
                By.CSS_SELECTOR, f".interest-card[data-cat='{category}']", 5
            )
            if card and self.click(card):
                selected += 1
        if not selected:
            self.fail("onboarding interests", "No .interest-card buttons found")
            return
        self.pass_("onboarding interests", f"Selected {selected} non-food interests")

        if not self.click_by_id("next-1", "onboarding next step 1"):
            return

        self.set_input_value("startDate", "")
        self.set_input_value("endDate", "")
        self.click_by_id("next-2", "onboarding negative missing dates continue")
        self.assert_visible_error_or_validation("onboarding negative missing dates")
        self.assert_no_500("onboarding negative missing dates")

        start = date.today() + timedelta(days=7)
        end = start + timedelta(days=1)
        self.set_input_value("startDate", end.isoformat())
        self.set_input_value("endDate", start.isoformat())
        self.click_by_id("next-2", "onboarding negative invalid date range continue")
        self.assert_visible_error_or_validation(
            "onboarding negative invalid date range"
        )
        self.assert_no_500("onboarding negative invalid date range")

        self.set_input_value("startDate", start.isoformat())
        self.set_input_value("endDate", end.isoformat())
        self.pass_("onboarding dates", f"Set {start.isoformat()} to {end.isoformat()}")

        if not self.click_by_id("next-2", "onboarding next step 2"):
            return
        if not self.click_by_id("next-3", "onboarding next step 3"):
            return

        rating = self.find(By.CSS_SELECTOR, ".rating-pill[data-rating='4.0']", 4)
        if rating:
            self.click(rating)
            self.pass_("onboarding rating", "Selected 4.0+ rating")
        else:
            self.warn("onboarding rating", "Rating pill not found; continuing")

        budget_max = self.find(By.ID, "budgetMax", 4)
        if budget_max:
            self.set_input_value("budgetMin", "6000")
            self.set_input_value("budgetMax", "1000")
            normalized = (
                self.driver.execute_script(
                    """
                const minEl = document.getElementById('budgetMin');
                const maxEl = document.getElementById('budgetMax');
                return minEl && maxEl ? Number(minEl.value) <= Number(maxEl.value) : null;
                """
                )
                if self.driver
                else None
            )
            if normalized:
                self.pass_(
                    "onboarding negative invalid budget",
                    "Budget sliders auto-normalized min/max safely",
                )
            else:
                self.warn(
                    "onboarding negative invalid budget",
                    "Budget min/max could be inverted or could not be verified",
                )
            self.set_input_value("budgetMax", "5000")
            self.pass_("onboarding budget", "Adjusted budget max")

        if not self.click_by_id("next-4", "onboarding next step 4"):
            return

        submit = self.visible(By.ID, "submit-btn", 8)
        if not submit or not self.click(submit):
            self.fail("onboarding submit", "Could not click Generate My Plan")
            return

        redirected = self.wait_url_contains("/daily-plan/", 15)
        if redirected:
            self.pass_(
                "onboarding submit",
                f"Preferences saved; redirected to {self.current_url()}",
            )
        else:
            msg = self.visible(By.ID, "pref-message", 3)
            detail = (
                msg.text.strip()
                if msg and msg.is_displayed()
                else f"Unexpected URL {self.current_url()}"
            )
            self.fail("onboarding submit", detail)
        self.check_console("onboarding")

    def click_by_id(self, element_id: str, check_name: str) -> bool:
        el = self.visible(By.ID, element_id, 8)
        if not el:
            self.fail(check_name, f"Missing #{element_id}")
            return False
        if not self.click(el):
            self.fail(check_name, f"Could not click #{element_id}")
            return False
        self.pass_(check_name, f"Clicked #{element_id}")
        return True

    def set_input_value(self, element_id: str, value: str) -> None:
        if not self.driver:
            return
        self.driver.execute_script(
            """
            const el = document.getElementById(arguments[0]);
            if (!el) return;
            el.value = arguments[1];
            el.dispatchEvent(new Event('input', {bubbles:true}));
            el.dispatchEvent(new Event('change', {bubbles:true}));
            """,
            element_id,
            value,
        )

    def explore_flow(self) -> None:
        self.goto("/events/page/")
        if "/login/" in self.current_url():
            self.fail(
                "explore access",
                "Explore redirected to login for authenticated test user",
            )
            return

        cards = self.wait_for_cards(".event-card", "explore event cards", timeout=25)
        if cards:
            self.pass_("explore cards", f"{len(cards)} event/place cards rendered")
        else:
            self.fail("explore cards", "No .event-card rendered")
            return

        search = self.visible(By.ID, "searchInput", 8)
        if search:
            search.clear()
            search.send_keys("park")
            self.wait_grid_settled()
            cards_after = self.all(By.CSS_SELECTOR, ".event-card")
            no_places = self.page_contains("No places found")
            if cards_after or no_places:
                self.pass_(
                    "explore search",
                    f"Search for 'park' completed; cards={len(cards_after)}, empty_state={no_places}",
                )
            else:
                self.warn(
                    "explore search",
                    "Search ran but no cards or empty-state text was detected",
                )

            clear = self.visible(By.ID, "clearSearchBtn", 4)
            if clear:
                self.click(clear)
                self.wait_grid_settled()
                self.pass_("explore clear search", "Clear search button worked")
            else:
                search.clear()
                self.warn(
                    "explore clear search",
                    "No visible clear button; cleared input directly",
                )
        else:
            self.fail("explore search", "Missing #searchInput")

        for cat in ["food", "culture", "nature", "heritage", "events"]:
            pill = self.find(By.CSS_SELECTOR, f".cat-pill[data-cat='{cat}']", 6)
            if not pill:
                self.warn(f"explore category {cat}", "Category pill missing")
                continue
            self.click(pill)
            self.wait_grid_settled()
            cards_now = self.all(By.CSS_SELECTOR, ".event-card")
            if cards_now or self.page_contains("No places found"):
                self.pass_(
                    f"explore category {cat}", f"Filter stable; cards={len(cards_now)}"
                )
            else:
                self.fail(
                    f"explore category {cat}", "Filter left grid in unknown state"
                )

        all_pill = self.find(By.CSS_SELECTOR, ".cat-pill[data-cat='']", 4)
        if all_pill:
            self.click(all_pill)
            self.wait_grid_settled()

        favs = [
            btn
            for btn in self.all(By.CSS_SELECTOR, ".event-card .fav-btn")
            if btn.is_displayed()
        ]
        if favs:
            before_text = favs[0].text.strip()
            if self.click(favs[0]):
                self.pause(0.8)
                if "/login/" in self.current_url():
                    self.fail(
                        "explore favorite button",
                        "Authenticated test user was redirected to login",
                    )
                else:
                    try:
                        after_text = (
                            favs[0].text.strip() if favs[0].is_displayed() else ""
                        )
                    except WebDriverException:
                        after_text = "rerendered"
                    self.pass_(
                        "explore favorite button",
                        f"Favorite button stayed in-app; state {before_text!r}->{after_text!r}",
                    )
            else:
                self.warn(
                    "explore favorite button",
                    "Favorite button was visible but could not be clicked",
                )
        else:
            self.warn(
                "explore favorite button", "No favorite buttons visible on event cards"
            )

        for context, selector in [
            ("explore map link", ".event-card .maps-link"),
            ("explore featured map link", "#trendingRow .maps-link"),
        ]:
            links = [
                link
                for link in self.all(By.CSS_SELECTOR, selector)
                if link.is_displayed()
            ]
            if links:
                href = links[0].get_attribute("href") or ""
                if href and "google.com/maps" in href:
                    self.pass_(context, f"Map href is present: {urlparse(href).netloc}")
                    self.open_external_link_safely(links[0], context)
                else:
                    self.fail(context, f"Map link missing/invalid href: {href!r}")
            else:
                self.warn(context, f"No visible links for selector {selector}")

        trending_adds = [
            btn
            for btn in self.all(By.CSS_SELECTOR, "#trendingRow .add-to-plan-btn")
            if btn.is_displayed()
        ]
        if trending_adds:
            label = trending_adds[0].text.strip()
            if self.click(trending_adds[0]):
                self.pause(0.8)
                if "/login/" in self.current_url():
                    self.fail(
                        "explore featured add button",
                        "Authenticated test user was redirected to login",
                    )
                else:
                    self.pass_(
                        "explore featured add button",
                        f"Clicked featured Add button safely ({label!r})",
                    )
            else:
                self.warn(
                    "explore featured add button",
                    "Featured Add button could not be clicked",
                )
        else:
            self.warn("explore featured add button", "No featured Add buttons visible")

        if self.all(By.CSS_SELECTOR, ".event-card") or self.page_contains(
            "No places found"
        ):
            self.pass_(
                "explore post-interaction stability",
                "Grid still shows cards or a clear empty state",
            )
        else:
            self.fail(
                "explore post-interaction stability",
                "Grid disappeared after interactions",
            )
        self.check_console("explore")

    def add_to_plan_flow(self) -> None:
        self.goto("/events/page/")
        cards = self.wait_for_cards(".event-card", "add to plan cards", timeout=20)
        if not cards:
            self.fail("add to plan", "No event cards available")
            return

        btns = self.all(By.CSS_SELECTOR, ".add-to-plan-btn")
        if not btns:
            self.warn("add to plan", "No Add buttons rendered on event cards")
            return

        if not self.click(btns[0]):
            self.fail("add to plan", "Could not click first Add button")
            return

        try:
            WebDriverWait(self.driver, 12).until(
                lambda d: "Added" in btns[0].text
                or "Added to your plan" in d.find_element(By.TAG_NAME, "body").text
                or "/login/" in d.current_url
            )
        except TimeoutException:
            pass

        if "/login/" in self.current_url():
            self.fail("add to plan", "Authenticated test user was redirected to login")
        elif "Added" in btns[0].text or self.page_contains("Added to your plan"):
            self.pass_("add to plan", "Event was added or success toast appeared")
        else:
            self.warn(
                "add to plan",
                "Clicked Add, but no explicit success toast/button state was detected",
            )
        self.check_console("add to plan")

    def daily_plan_flow(self) -> None:
        self.goto("/daily-plan/")
        if "/login/" in self.current_url():
            self.fail(
                "daily plan access", "Authenticated test user was redirected to login"
            )
            return

        if self.visible(By.ID, "timeline", 15) or self.visible(By.ID, "emptyState", 5):
            self.pass_("daily plan shell", "Timeline/empty-state container is present")
        else:
            self.fail("daily plan shell", "Timeline and empty-state containers missing")

        gen = self.visible(By.ID, "generate-plan-btn", 10)
        if not gen:
            self.fail("daily plan generate button", "Missing #generate-plan-btn")
            return
        self.pass_("daily plan generate button", "Generate Plan button exists")

        if self.click(gen):
            self.wait_daily_plan_result()
        else:
            self.fail("daily plan generate", "Could not click Generate Plan")

        activities = self.all(
            By.CSS_SELECTOR,
            "#timeline article, #timeline [data-event-id], #timeline button",
        )
        message = self.visible(By.ID, "plan-message", 2)
        visible_message = (
            message.text.strip() if message and message.is_displayed() else ""
        )
        if self.all(By.CSS_SELECTOR, "#timeline article"):
            self.pass_("daily plan result", f"Activities/timeline cards appeared")
        elif visible_message:
            if (
                "Could not" in visible_message
                or "No places" in visible_message
                or "preferences" in visible_message
            ):
                self.warn(
                    "daily plan result", f"Clear user-facing message: {visible_message}"
                )
            else:
                self.pass_(
                    "daily plan result", f"User-facing message: {visible_message}"
                )
        elif activities:
            self.pass_(
                "daily plan result", "Timeline controls rendered after generation"
            )
        else:
            self.fail(
                "daily plan result",
                "No activities and no clear user-facing message after generation",
            )

        self.validate_daily_plan_slot_categories()
        self.daily_plan_day_tabs()
        self.daily_plan_add_activity_modal()
        self.daily_plan_route_button()
        self.optional_activity_mutations()
        self.check_console("daily plan")

    def validate_daily_plan_slot_categories(self) -> None:
        if not self.driver:
            return
        try:
            slot_texts = self.driver.execute_script(
                "return Array.from(document.querySelectorAll('#timeline > div')).map(el => el.innerText);"
            )
        except WebDriverException as exc:
            self.warn(
                "daily plan slot categories",
                f"Could not inspect visible slot text: {exc}",
            )
            return
        if not slot_texts:
            self.warn("daily plan slot categories", "No visible slot cards to inspect")
            return

        failures = []
        for text in slot_texts:
            lowered = str(text).lower()
            is_placeholder = "no activity for this slot" in lowered
            if "lunch" in lowered and not is_placeholder and "food" not in lowered:
                failures.append(
                    f"Lunch slot is not visibly Food: {str(text).splitlines()[:4]}"
                )
            if "activity" in lowered and not is_placeholder and "food" in lowered:
                failures.append(
                    f"Activity slot is visibly Food without Food preference: {str(text).splitlines()[:4]}"
                )
        if failures:
            self.fail("daily plan slot categories", "; ".join(failures[:2]))
        else:
            self.pass_(
                "daily plan slot categories",
                "Visible Lunch/Activity categories respect non-food preferences",
            )

    def optional_activity_mutations(self) -> None:
        actions = [
            ("daily plan try another", ".try-another-btn"),
            ("daily plan remove", ".remove-btn"),
        ]
        clicked_any = False
        for name, selector in actions:
            buttons = [
                btn for btn in self.all(By.CSS_SELECTOR, selector) if btn.is_displayed()
            ]
            if not buttons:
                self.warn(name, f"No optional {selector} buttons visible")
                continue
            label = buttons[0].text.strip() or selector
            if self.click(buttons[0]):
                clicked_any = True
                time.sleep(1 if self.slow else 0.5)
                if "/daily-plan/" in self.current_url():
                    self.pass_(
                        name, f"Clicked optional '{label}' and page remained stable"
                    )
                else:
                    self.fail(
                        name,
                        f"After clicking '{label}', URL changed to {self.current_url()}",
                    )
            else:
                self.warn(name, f"Optional button '{label}' could not be clicked")
        if clicked_any:
            self.assert_no_500("daily plan replace/remove")

    def daily_plan_day_tabs(self) -> None:
        tabs = [
            tab
            for tab in self.all(By.CSS_SELECTOR, "#dayTabs button")
            if tab.is_displayed()
        ]
        if not tabs:
            self.warn("daily plan day tabs", "No day tabs visible")
            return
        tested = 0
        for index in range(min(2, len(tabs))):
            current_tabs = [
                tab
                for tab in self.all(By.CSS_SELECTOR, "#dayTabs button")
                if tab.is_displayed()
            ]
            if index >= len(current_tabs):
                break
            tab = current_tabs[index]
            try:
                label = tab.text.strip() or "day tab"
            except WebDriverException:
                label = "day tab"
            if self.click(tab):
                tested += 1
                self.pause(0.4)
                if "/daily-plan/" in self.current_url():
                    self.pass_("daily plan day tabs", f"Clicked {label!r} safely")
                else:
                    self.fail(
                        "daily plan day tabs",
                        f"Day tab changed URL unexpectedly: {self.current_url()}",
                    )
        if tested == 0:
            self.warn(
                "daily plan day tabs", "Day tabs were visible but could not be clicked"
            )

    def daily_plan_add_activity_modal(self) -> None:
        btn = self.visible(By.ID, "add-activity-btn", 5)
        if not btn:
            self.warn("daily plan add activity modal", "Add Activity button missing")
            return
        if not self.click(btn):
            self.warn(
                "daily plan add activity modal", "Could not open Add Activity modal"
            )
            return
        modal = self.visible(By.ID, "addActivityModal", 6)
        if not modal:
            self.fail(
                "daily plan add activity modal",
                "Add Activity modal did not become visible",
            )
            return
        self.pass_("daily plan add activity modal", "Modal opened")

        search = self.visible(By.ID, "activitySearchInput", 4)
        if search:
            search.clear()
            search.send_keys("zzzz-no-place-e2e")
            self.wait_activity_search_result("No results found", 8)
            if self.page_contains("No results found"):
                self.pass_(
                    "daily plan add activity bad search",
                    "Bad search produced clear no-results message",
                )
            else:
                self.warn(
                    "daily plan add activity bad search",
                    "No-results message was not visible after bad search",
                )

            search.clear()
            search.send_keys("park")
            self.wait_activity_cards(10)
            results = [
                el
                for el in self.all(
                    By.CSS_SELECTOR, "#activitySearchResults [data-event-id]"
                )
                if el.is_displayed()
            ]
            if results:
                self.pass_(
                    "daily plan add activity good search",
                    f"Good search returned {len(results)} result(s)",
                )
                if self.click(results[0]):
                    self.pause(1.2)
                    self.pass_(
                        "daily plan add activity select",
                        "Clicked one search result for the test user's plan",
                    )
                else:
                    self.warn(
                        "daily plan add activity select",
                        "Search result was visible but could not be clicked",
                    )
            else:
                self.warn(
                    "daily plan add activity good search",
                    "Good search returned no visible results",
                )
        else:
            self.warn("daily plan add activity search", "Search input missing in modal")

        close = self.visible(By.ID, "closeAddActivity", 3)
        if close:
            self.click(close)
            self.pass_("daily plan add activity close", "Close modal button clicked")
        self.assert_no_500("daily plan add activity modal")

    def daily_plan_route_button(self) -> None:
        buttons = [
            btn
            for btn in self.all(By.CSS_SELECTOR, "#openRouteBtn, .navigate-btn")
            if btn.is_displayed()
        ]
        if not buttons:
            self.warn("daily plan route button", "No route/navigation button visible")
            return
        btn = buttons[0]
        href = (
            btn.get_attribute("data-route-url")
            or btn.get_attribute("data-navigate-url")
            or ""
        )
        if href:
            self.pass_(
                "daily plan route button",
                f"Route URL present for {urlparse(href).netloc or 'route'}",
            )
            if self.driver:
                original = self.driver.current_window_handle
                handles_before = set(self.driver.window_handles)
                try:
                    self.driver.execute_script(
                        "window.open(arguments[0], '_blank', 'noopener,noreferrer');",
                        href,
                    )
                    WebDriverWait(self.driver, 5).until(
                        lambda d: len(set(d.window_handles) - handles_before) >= 1
                    )
                    new_handle = list(set(self.driver.window_handles) - handles_before)[
                        0
                    ]
                    self.driver.switch_to.window(new_handle)
                    self.pass_(
                        "daily plan route button external",
                        "Route opened in a temporary tab",
                    )
                    self.driver.close()
                    self.driver.switch_to.window(original)
                except Exception as exc:
                    try:
                        self.driver.switch_to.window(original)
                    except Exception:
                        pass
                    self.warn(
                        "daily plan route button external",
                        f"Could not open route safely: {type(exc).__name__}: {exc}",
                    )
        else:
            self.warn(
                "daily plan route button",
                "Route button visible but no route URL data attribute found",
            )

    def wait_activity_search_result(self, expected_text: str, timeout: int = 8) -> None:
        if not self.driver:
            return
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda d: expected_text.lower()
                in d.find_element(By.ID, "activitySearchResults").text.lower()
            )
        except TimeoutException:
            pass

    def wait_activity_cards(self, timeout: int = 8) -> None:
        if not self.driver:
            return
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda d: d.find_elements(
                    By.CSS_SELECTOR, "#activitySearchResults [data-event-id]"
                )
                or "No results found"
                in d.find_element(By.ID, "activitySearchResults").text
            )
        except TimeoutException:
            pass

    def optional_pages_flow(self) -> None:
        for path in [
            "/booking/",
            "/car-rental/",
            "/travel-guide/",
            "/settings/",
            "/profile/",
        ]:
            self.goto(path)
            self.wait_document_ready()
            if self.status_from_browser() == 404 or "Not Found" in (
                self.driver.title if self.driver else ""
            ):
                self.warn(f"optional page {path}", "Route missing / 404")
                continue
            if "/login/" in self.current_url():
                self.warn(f"optional page {path}", "Redirected to login")
                continue
            h1 = self.find(By.TAG_NAME, "h1", 5)
            main_text = self.body_text()[:120].replace("\n", " ")
            if h1 and h1.text.strip():
                self.pass_(f"optional page {path}", f"H1: {h1.text.strip()[:80]}")
            elif main_text:
                self.pass_(
                    f"optional page {path}", f"Main content present: {main_text}"
                )
            else:
                self.fail(f"optional page {path}", "No visible title/H1/main content")
            self.check_console(f"optional {path}")

    def profile_settings_flow(self) -> None:
        self.goto("/profile/")
        if "/login/" in self.current_url():
            self.fail(
                "profile load after login",
                "Profile redirected to login for authenticated test user",
            )
            return
        self.assert_no_500("profile load after login")
        if self.find(By.TAG_NAME, "h1", 5) or self.page_contains("My Preferences"):
            self.pass_("profile load after login", "Profile page content is visible")
        else:
            self.fail(
                "profile load after login",
                "Profile page did not show recognizable content",
            )

        edit = self.find(
            By.XPATH,
            "//a[contains(normalize-space(.), 'Edit Preferences') or contains(normalize-space(.), 'Set them now')]",
            5,
        )
        if edit and self.click(edit):
            if "/onboarding/" in self.current_url():
                self.pass_(
                    "profile edit preferences",
                    "Edit Preferences navigates to onboarding/preferences",
                )
            else:
                self.fail(
                    "profile edit preferences",
                    f"Unexpected target URL: {self.current_url()}",
                )
            self.goto("/profile/")
        else:
            self.warn(
                "profile edit preferences", "Edit Preferences link not found/clickable"
            )
        self.check_console("profile")

        self.goto("/settings/")
        if "/login/" in self.current_url():
            self.fail(
                "settings load after login",
                "Settings redirected to login for authenticated test user",
            )
            return
        self.assert_no_500("settings load after login")
        if self.find(By.TAG_NAME, "h1", 5) or self.page_contains("Settings"):
            self.pass_("settings load after login", "Settings page content is visible")
        else:
            self.fail(
                "settings load after login",
                "Settings page did not show recognizable content",
            )

        lang_en = self.visible(By.ID, "langEn", 4)
        if lang_en:
            self.click(lang_en)
            self.pass_(
                "settings language toggle", "Clicked English language toggle safely"
            )
            self.dismiss_alert_if_present("settings language toggle")
        else:
            self.warn("settings language toggle", "English language toggle missing")

        theme = self.visible(By.ID, "themeDark", 4) or self.visible(
            By.ID, "themeLight", 4
        )
        if theme:
            self.click(theme)
            self.pass_("settings theme toggle", "Clicked a theme toggle safely")
        else:
            self.warn("settings theme toggle", "Theme toggles missing")

        save = self.visible(By.ID, "saveSettingsBtn", 4)
        if save:
            if save.is_enabled():
                self.click(save)
                self.pass_("settings save button", "Clicked Save Settings safely")
            else:
                self.warn(
                    "settings save button", "Save Settings button present but disabled"
                )
        else:
            self.warn("settings save button", "Save Settings button missing")
        self.check_console("settings")

    def button_audit_flow(self) -> None:
        for path in [
            "/",
            "/login/",
            "/signup/",
            "/events/page/",
            "/daily-plan/",
            "/booking/",
            "/car-rental/",
            "/travel-guide/",
            "/settings/",
            "/profile/",
        ]:
            self.audit_page_buttons(path)

    def audit_page_buttons(self, path: str) -> None:
        self.goto(path)
        self.wait_document_ready()
        if self.status_from_browser() == 404 or "Not Found" in (
            self.driver.title if self.driver else ""
        ):
            self.warn(
                f"button audit {path}",
                "Skipped missing/404 route",
                section="button audit",
            )
            return
        controls = [
            el
            for el in self.all(By.CSS_SELECTOR, "button, a[href]")
            if self.is_visible_control(el)
        ]
        visible_total = len(controls)
        tested = 0
        skipped = 0
        failures = 0
        max_clicks = 3

        index = 0
        while index < visible_total:
            current_controls = [
                el
                for el in self.all(By.CSS_SELECTOR, "button, a[href]")
                if self.is_visible_control(el)
            ]
            if index >= len(current_controls):
                break
            control = current_controls[index]
            index += 1
            try:
                label = self.control_label(control)
                tag = (control.tag_name or "").lower()
                href = control.get_attribute("href") or ""
            except WebDriverException:
                skipped += 1
                continue
            kind, reason = self.classify_control(control, label, href)

            if href and ("/api/auth/login/" in href or "/api/auth/signup/" in href):
                failures += 1
                self.fail(
                    f"button audit {path} api auth link",
                    f"Visible control {label!r} points to API auth URL: {urlparse(href).path}",
                    section="button audit",
                )
                continue

            if kind == "external":
                if href and href != "#":
                    self.pass_(
                        f"button audit {path} external href",
                        f"{label!r} has href {urlparse(href).netloc}",
                        section="button audit",
                    )
                else:
                    failures += 1
                    self.fail(
                        f"button audit {path} external href",
                        f"{label!r} external link missing href",
                        section="button audit",
                    )
                continue

            if kind == "skip":
                skipped += 1
                continue

            if tested >= max_clicks:
                skipped += 1
                continue

            restore = path
            before = self.current_url()
            if self.safe_click_button(
                control, f"button audit {path} {label}", restore_url=restore
            ):
                tested += 1
                if (
                    "/api/auth/login/" in self.current_url()
                    or "/api/auth/signup/" in self.current_url()
                ):
                    failures += 1
                    self.fail(
                        f"button audit {path} api navigation",
                        f"Clicked {label!r} and reached API auth URL",
                        section="button audit",
                    )
                elif tag == "a" and before != self.current_url():
                    self.pass_(
                        f"button audit {path} internal navigation",
                        f"Clicked {label!r} safely",
                        section="button audit",
                    )
            else:
                skipped += 1

        detail = f"visible={visible_total}, tested={tested}, skipped={skipped}, failures={failures}"
        if failures:
            self.fail(f"button audit {path}", detail, section="button audit")
        elif tested:
            self.pass_(f"button audit {path}", detail, section="button audit")
        else:
            self.warn(f"button audit {path}", detail, section="button audit")

    def is_visible_control(self, element: WebElement) -> bool:
        try:
            return (
                element.is_displayed()
                and element.size.get("height", 0) > 0
                and element.size.get("width", 0) > 0
            )
        except WebDriverException:
            return False

    def control_label(self, element: WebElement) -> str:
        try:
            label = (
                element.text.strip()
                or element.get_attribute("aria-label")
                or element.get_attribute("title")
                or element.get_attribute("id")
                or element.get_attribute("class")
                or element.tag_name
            )
        except WebDriverException:
            label = "control"
        return " ".join(str(label).split())[:80] or "control"

    def classify_control(
        self, element: WebElement, label: str, href: str
    ) -> tuple[str, str]:
        lowered = f"{label} {href}".lower()
        tag = (element.tag_name or "").lower()
        destructive = (
            "logout",
            "delete",
            "remove",
            "clear cache",
            "password",
            "submitpwd",
        )
        heavy_actions = (
            "add",
            "generate",
            "save",
            "create account",
            "login",
            "signup",
            "book",
            "rent",
            "load more",
            "open route",
        )
        if any(word in lowered for word in destructive):
            return "skip", "destructive or auth-ending"
        if href:
            parsed = urlparse(href)
            if (
                parsed.scheme in ("http", "https")
                and parsed.netloc
                and parsed.netloc != urlparse(self.base_url).netloc
            ):
                return "external", "external link"
            if href.endswith("#") or parsed.path == "":
                return "skip", "placeholder link"
            return "click", "internal navigation"
        if tag == "button":
            button_type = (element.get_attribute("type") or "submit").lower()
            if button_type == "submit":
                return "skip", "form submit"
            if any(word in lowered for word in heavy_actions):
                return "skip", "stateful/heavy action"
            return "click", "safe action/toggle"
        return "skip", "unsupported control"

    def dismiss_alert_if_present(self, context: str) -> None:
        if not self.driver:
            return
        try:
            alert = WebDriverWait(self.driver, 1).until(EC.alert_is_present())
            alert.dismiss()
            self.pass_(f"{context} alert", "Dismissed browser alert safely")
        except TimeoutException:
            return
        except WebDriverException as exc:
            self.warn(f"{context} alert", f"Could not dismiss alert: {exc}")

    def logout_flow(self) -> None:
        self.goto("/profile/")
        if "/login/" in self.current_url():
            self.warn("logout", "Already logged out before logout flow")
        else:
            btn = self.find(
                By.XPATH,
                "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'logout')]",
                5,
            )
            if btn and self.click(btn):
                self.wait_url_contains("/login/", 10)
                self.pass_(
                    "logout click", f"Clicked logout; current URL {self.current_url()}"
                )
            else:
                self.goto("/logout/")
                self.wait_url_contains("/login/", 10)
                self.pass_(
                    "logout fallback",
                    f"Visited /logout/; current URL {self.current_url()}",
                )

        self.goto("/daily-plan/")
        if "/login/" in self.current_url():
            self.pass_(
                "post-logout protected redirect",
                "Protected page redirected to login after logout",
            )
        else:
            self.fail(
                "post-logout protected redirect",
                f"Protected page did not redirect after logout: {self.current_url()}",
            )

    def wait_for_cards(
        self, selector: str, name: str, timeout: int = 15
    ) -> list[WebElement]:
        if not self.driver:
            return []
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, selector))
            )
        except TimeoutException:
            self.warn(name, f"No cards matching {selector} within {timeout}s")
        return self.all(By.CSS_SELECTOR, selector)

    def wait_grid_settled(self) -> None:
        if not self.driver:
            return
        try:
            WebDriverWait(self.driver, 12).until(
                lambda d: d.find_elements(By.CSS_SELECTOR, ".event-card")
                or "No places found" in d.find_element(By.TAG_NAME, "body").text
            )
        except TimeoutException:
            pass
        self.pause()

    def wait_daily_plan_result(self) -> None:
        if not self.driver:
            return
        try:
            WebDriverWait(self.driver, 25).until(
                lambda d: d.find_elements(By.CSS_SELECTOR, "#timeline article")
                or (
                    d.find_elements(By.ID, "plan-message")
                    and d.find_element(By.ID, "plan-message").is_displayed()
                    and d.find_element(By.ID, "plan-message").text.strip()
                )
                or (
                    d.find_elements(By.ID, "emptyState")
                    and d.find_element(By.ID, "emptyState").is_displayed()
                )
            )
        except TimeoutException:
            pass

    def page_contains(self, text: str) -> bool:
        return text.lower() in self.body_text().lower()

    def body_text(self) -> str:
        if not self.driver:
            return ""
        try:
            return self.driver.find_element(By.TAG_NAME, "body").text
        except NoSuchElementException:
            return ""

    def status_from_browser(self) -> int | None:
        if not self.driver:
            return None
        try:
            value = self.driver.execute_script(
                "return document.title.includes('404') || document.body.innerText.includes('Not Found') ? 404 : 200;"
            )
            return int(value)
        except (JavascriptException, WebDriverException, TypeError, ValueError):
            return None

    def write_reports(self) -> None:
        counts = self.counts()
        sections = self.section_counts()
        verdict = self.verdict()
        payload = {
            "base_url": self.base_url,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "test_email": self.test_email,
            "counts": counts,
            "sections": sections,
            "verdict": verdict,
            "results": [asdict(result) for result in self.results],
        }
        JSON_REPORT.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        lines = [
            "Tizahab Render E2E Report",
            f"URL: {self.base_url}",
            f"Created: {payload['created_at']}",
            f"Test user: {self.test_email}",
            "",
            f"Total checks: {counts['total']}",
            f"Passed: {counts['passed']}",
            f"Warnings: {counts['warnings']}",
            f"Failed: {counts['failed']}",
            f"Final verdict: {verdict}",
            "",
            "Sections:",
        ]
        for section, section_counts in sections.items():
            lines.append(
                f"- {section}: total={section_counts['total']}, "
                f"pass={section_counts['passed']}, warn={section_counts['warnings']}, fail={section_counts['failed']}"
            )
        lines.extend(
            [
                "",
                "Results:",
            ]
        )
        for i, result in enumerate(self.results, 1):
            lines.append(
                f"{i:02d}. [{result.status}] ({result.section}) {result.name}: {result.detail}"
            )
            if result.url:
                lines.append(f"    URL: {result.url}")
            if result.screenshot:
                lines.append(f"    Screenshot: {result.screenshot}")
            if result.console_errors:
                for err in result.console_errors[:3]:
                    lines.append(f"    Console: {err}")
        TEXT_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def counts(self) -> dict[str, int]:
        return {
            "total": len(self.results),
            "passed": sum(1 for item in self.results if item.status == "PASS"),
            "warnings": sum(1 for item in self.results if item.status == "WARN"),
            "failed": sum(1 for item in self.results if item.status == "FAIL"),
        }

    def section_counts(self) -> dict[str, dict[str, int]]:
        sections: dict[str, dict[str, int]] = {}
        for item in self.results:
            bucket = sections.setdefault(
                item.section, {"total": 0, "passed": 0, "warnings": 0, "failed": 0}
            )
            bucket["total"] += 1
            if item.status == "PASS":
                bucket["passed"] += 1
            elif item.status == "WARN":
                bucket["warnings"] += 1
            elif item.status == "FAIL":
                bucket["failed"] += 1
        for section in [
            "positive path",
            "negative validation",
            "button audit",
            "api category validation",
            "console errors",
        ]:
            sections.setdefault(
                section, {"total": 0, "passed": 0, "warnings": 0, "failed": 0}
            )
        return dict(sorted(sections.items()))

    def verdict(self) -> str:
        counts = self.counts()
        if counts["failed"]:
            return "NOT SAFE TO DEMO"
        if counts["warnings"]:
            return "SAFE WITH WARNINGS"
        return "SAFE TO DEMO"

    def print_summary(self) -> None:
        counts = self.counts()
        print("\n" + "=" * 72)
        print("TIZAHAB RENDER E2E SUMMARY")
        print("=" * 72)
        print(f"URL: {self.base_url}")
        print(f"total checks: {counts['total']}")
        print(f"passed:       {counts['passed']}")
        print(f"warnings:     {counts['warnings']}")
        print(f"failed:       {counts['failed']}")
        print(f"final verdict: {self.verdict()}")
        print(f"json report:  {JSON_REPORT}")
        print(f"text report:  {TEXT_REPORT}")
        print("=" * 72)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Tizahab Render production E2E test suite"
    )
    parser.add_argument(
        "--url", default=DEFAULT_URL, help=f"Base URL to test (default: {DEFAULT_URL})"
    )
    parser.add_argument(
        "--headless", action="store_true", help="Run Chrome in headless mode"
    )
    parser.add_argument(
        "--slow",
        action="store_true",
        help="Slow down interactions for visual debugging",
    )
    return parser.parse_args()


def main() -> int:
    if MISSING_DEPS:
        print("Missing Python dependencies:", ", ".join(sorted(set(MISSING_DEPS))))
        print("Install with:")
        print("    pip install selenium webdriver-manager requests")
        return 2

    args = parse_args()
    tester = RenderJourneyTester(
        base_url=args.url, headless=args.headless, slow=args.slow
    )
    tester.run()
    return 1 if tester.counts()["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
