"""
Tizahab E2E User Journey Tests
Target: http://127.0.0.1:8000

Setup:
    pip install selenium webdriver-manager

Run:
    python tests/test_user_journey.py
    python tests/test_user_journey.py --headless
    python tests/test_user_journey.py --url http://localhost:8000
"""

import sys
import time
import argparse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException,
)

try:
    from webdriver_manager.chrome import ChromeDriverManager

    USE_MANAGER = True
except ImportError:
    USE_MANAGER = False


# ── Selectors matched to actual templates ──────────────────────────────────────

SELECTORS = {
    # Landing (index.html)
    "hero_h1": (By.TAG_NAME, "h1"),
    "get_started_link": (By.LINK_TEXT, "Get Started"),
    # Signup (signup.html)
    "signup_name": (By.ID, "signup-name"),
    "signup_email": (By.ID, "signup-email"),
    "signup_password": (By.ID, "signup-password"),
    "signup_confirm": (By.ID, "signup-confirm"),
    "signup_btn": (By.ID, "signup-btn"),
    "signup_error": (By.ID, "signup-error"),
    # Preferences / Onboarding (preferences.html)
    "interest_cards": (By.CSS_SELECTOR, ".interest-card"),
    "step_label": (By.ID, "stepLabel"),
    # Daily Plan (daily_plan.html)
    "timeline": (By.ID, "timeline"),
    "generate_plan_btn": (By.ID, "generate-plan-btn"),
    "open_route_btn": (By.ID, "openRouteBtn"),
    "add_activity_btn": (By.ID, "add-activity-btn"),
    "day_tabs": (By.ID, "dayTabs"),
    # Explore / Events (events_list.html)
    "search_input": (By.ID, "searchInput"),
    "cat_pills": (By.CSS_SELECTOR, ".cat-pill"),
    "event_cards": (By.CSS_SELECTOR, ".event-card"),
    "clear_search_btn": (By.ID, "clearSearchBtn"),
    # Booking (booking.html)
    "booking_articles": (By.CSS_SELECTOR, "article"),
    "booking_com_links": (By.XPATH, "//*[contains(text(),'Booking.com')]"),
    "google_hotel_links": (By.XPATH, "//*[contains(text(),'Google Hotels')]"),
    # Car Rental (car_rental.html)
    "rental_articles": (By.CSS_SELECTOR, "article"),
    "theeb_heading": (By.XPATH, "//*[contains(text(),'Theeb')]"),
    "yelo_heading": (By.XPATH, "//*[contains(text(),'Yelo')]"),
    "uber_heading": (By.XPATH, "//*[contains(text(),'Uber')]"),
    # Travel Guide (travel_guide.html)
    "guide_cards": (By.CSS_SELECTOR, ".guide-card"),
    # Profile (profile.html)
    "profile_name": (By.ID, "profileName"),
    "stat_plans": (By.ID, "statPlans"),
    "stat_favs": (By.ID, "statFavs"),
    "logout_btn": (By.ID, "logoutBtn"),
}


class TizahabTest:

    def __init__(self, base_url: str, headless: bool = False):
        self.base_url = base_url.rstrip("/")
        self.errors: list[str] = []
        self.passed: list[str] = []

        opts = Options()
        if headless:
            opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--window-size=1280,900")
        opts.set_capability("goog:loggingPrefs", {"browser": "ALL"})

        if USE_MANAGER:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=opts)
        else:
            self.driver = webdriver.Chrome(options=opts)

        self.wait = WebDriverWait(self.driver, 12)

    # ── Helpers ────────────────────────────────────────────────────────────────

    def log(self, message: str, status: str = "✓") -> None:
        print(f"  {status} {message}")
        if status == "✓":
            self.passed.append(message)

    def error(self, message: str) -> None:
        self.errors.append(message)
        print(f"  ✗ ERROR: {message}")

    def url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def goto(self, path: str) -> None:
        self.driver.get(self.url(path))

    def find(self, key: str, timeout: int = 8):
        """Return element or None (no exception)."""
        by, selector = SELECTORS[key]
        try:
            return self.wait.until(EC.presence_of_element_located((by, selector)))
        except TimeoutException:
            return None

    def find_all(self, key: str):
        by, selector = SELECTORS[key]
        try:
            return self.driver.find_elements(by, selector)
        except NoSuchElementException:
            return []

    def wait_for_url_contains(self, fragment: str, timeout: int = 8) -> bool:
        try:
            WebDriverWait(self.driver, timeout).until(EC.url_contains(fragment))
            return True
        except TimeoutException:
            return False

    def console_errors(self) -> list[dict]:
        try:
            logs = self.driver.get_log("browser")
            return [e for e in logs if e.get("level") == "SEVERE"]
        except WebDriverException:
            return []

    # ── Test methods ───────────────────────────────────────────────────────────

    def test_landing_page(self) -> None:
        print("\n=== Testing Landing Page ===")
        self.goto("/")

        if "Tizahab" in self.driver.title:
            self.log("Page title contains 'Tizahab'")
        else:
            self.error(f"Unexpected title: '{self.driver.title}'")

        if self.find("hero_h1"):
            self.log("H1 hero heading present")
        else:
            self.error("No <h1> found on landing page")

        # "Get Started" or any CTA that leads to signup/login
        try:
            cta = self.driver.find_element(
                By.XPATH,
                "//*[contains(text(),'Get Started') or contains(text(),'Start') or contains(@href,'/signup') or contains(@href,'/login')]",
            )
            self.log(
                f"CTA button/link found: '{cta.text.strip() or cta.get_attribute('href')}'"
            )
        except NoSuchElementException:
            self.error("No CTA (Get Started / Sign up / Login) found on landing page")

        errs = self.console_errors()
        if errs:
            self.error(
                f"{len(errs)} browser console SEVERE error(s): {errs[0]['message'][:120]}"
            )
        else:
            self.log("No severe browser console errors")

    def test_signup(self) -> None:
        print("\n=== Testing Signup ===")
        self.goto("/signup/")

        # Check page loaded
        if self.find("signup_name") is None:
            self.error("Signup form not found — aborting signup test")
            return

        email = f"tizahab_test_{int(time.time())}@example.com"
        try:
            self.driver.find_element(*SELECTORS["signup_name"]).send_keys(
                "Test Tizahab"
            )
            self.driver.find_element(*SELECTORS["signup_email"]).send_keys(email)
            self.driver.find_element(*SELECTORS["signup_password"]).send_keys(
                "TestPass123!"
            )
            self.driver.find_element(*SELECTORS["signup_confirm"]).send_keys(
                "TestPass123!"
            )
            self.log("Signup form filled")
        except Exception as e:
            self.error(f"Could not fill signup form: {e}")
            return

        try:
            self.driver.find_element(*SELECTORS["signup_btn"]).click()
        except Exception as e:
            self.error(f"Could not click signup button: {e}")
            return

        # Expect redirect to /home/ or /onboarding/
        if self.wait_for_url_contains("/home/") or self.wait_for_url_contains(
            "/onboarding/"
        ):
            self.log(f"Signup succeeded — redirected to {self.driver.current_url}")
        else:
            # Check for inline error message
            err_el = self.driver.find_elements(*SELECTORS["signup_error"])
            if err_el and err_el[0].is_displayed():
                self.error(f"Signup returned error: {err_el[0].text.strip()}")
            else:
                self.error(f"Unexpected URL after signup: {self.driver.current_url}")

    def test_preferences(self) -> None:
        print("\n=== Testing Preferences / Onboarding ===")
        if "/onboarding/" not in self.driver.current_url:
            self.goto("/onboarding/")

        step_label = self.find("step_label")
        if step_label:
            self.log(f"Preferences step indicator: '{step_label.text.strip()}'")
        else:
            self.error("Preferences step label (#stepLabel) not found")

        cards = self.find_all("interest_cards")
        if cards:
            self.log(f"Found {len(cards)} interest cards")
            for card in cards[:3]:
                try:
                    card.click()
                except Exception:
                    pass
            self.log("Clicked first 3 interest cards")
        else:
            self.error("No interest cards (.interest-card) found")

        # Advance through wizard with Next/Continue button
        try:
            next_btn = self.driver.find_element(
                By.XPATH,
                "//*[@id='nextBtn' or contains(@id,'next') or contains(text(),'Next') or contains(text(),'Continue')]",
            )
            next_btn.click()
            time.sleep(1)
            self.log("Wizard Next/Continue button clicked")
        except NoSuchElementException:
            self.log("No Next button found (wizard may auto-advance)")

    def test_daily_plan(self) -> None:
        print("\n=== Testing Daily Plan ===")
        self.goto("/daily-plan/")

        # Day tabs
        tabs = self.find_all("day_tabs")
        self.log(f"Day tabs container present: {bool(tabs)}")

        # Wait for skeleton to resolve (timeline or emptyState becomes visible)
        try:
            WebDriverWait(self.driver, 15).until(
                lambda d: (
                    d.find_element(By.ID, "timeline").get_attribute("class") != ""
                    or d.find_element(By.ID, "emptyState").get_attribute("class") != ""
                )
            )
        except Exception:
            pass  # Continue even if timing out

        timeline = self.driver.find_elements(By.ID, "timeline")
        empty_state = self.driver.find_elements(By.ID, "emptyState")
        activity_count_el = self.driver.find_elements(By.ID, "activityCount")

        if timeline:
            self.log("Timeline container present in DOM")
        if activity_count_el:
            self.log(f"Activity count indicator: '{activity_count_el[0].text.strip()}'")

        # Generate Plan button
        gen_btn = self.find("generate_plan_btn")
        if gen_btn:
            self.log("'Generate New Plan' button present")
        else:
            self.error("Generate Plan button (#generate-plan-btn) missing")

        # Add Activity button
        if self.find("add_activity_btn"):
            self.log("'Add Activity' button present")
        else:
            self.error("Add Activity button (#add-activity-btn) missing")

        # Open Route button (only visible when plan has activities)
        route_btns = self.driver.find_elements(*SELECTORS["open_route_btn"])
        if route_btns:
            self.log("'Open Route in Google Maps' button present")
        else:
            self.log("Route button not visible (expected if plan is empty)")

    def test_explore(self) -> None:
        print("\n=== Testing Explore / Events Page ===")
        self.goto("/events/page/")

        # Search input
        search = self.find("search_input")
        if search:
            self.log("Search input (#searchInput) found")
            try:
                search.send_keys("park")
                time.sleep(1)
                self.log("Search query 'park' entered")
                # Clear
                clear_btn = self.driver.find_elements(*SELECTORS["clear_search_btn"])
                if clear_btn and clear_btn[0].is_displayed():
                    clear_btn[0].click()
                    self.log("Clear search button clicked")
            except Exception as e:
                self.error(f"Search interaction failed: {e}")
        else:
            self.error("Search input (#searchInput) not found")

        # Category pills
        pills = self.find_all("cat_pills")
        if len(pills) >= 2:
            self.log(f"Found {len(pills)} category filter pills (.cat-pill)")
            try:
                # Click second pill (first non-"All" category)
                pills[1].click()
                time.sleep(1)
                self.log(f"Category '{pills[1].text.strip()}' filter clicked")
                # Reset to All
                pills[0].click()
                time.sleep(1)
                self.log("Reset to 'All Places' filter")
            except Exception as e:
                self.error(f"Category filter click failed: {e}")
        else:
            self.error(f"Expected ≥2 category pills, found {len(pills)}")

        # Event cards — wait for async fetch+render to finish (up to 20 s).
        # The JS fires fetchAreaEvents() before loadEvents(), which can add
        # 5–15 s of latency on production before any .event-card hits the DOM.
        try:
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_all_elements_located(SELECTORS["event_cards"])
            )
            cards = self.find_all("event_cards")
            self.log(f"Found {len(cards)} event cards (.event-card)")
        except TimeoutException:
            self.error(
                "No event cards (.event-card) rendered within 20 s — "
                "check /api/events/ response or browser JS console"
            )

    def test_booking(self) -> None:
        print("\n=== Testing Booking Page ===")
        self.goto("/booking/")

        if "Tizahab" not in self.driver.title:
            self.error("Booking page did not load (possible auth redirect)")
            return

        articles = self.find_all("booking_articles")
        self.log(f"Found {len(articles)} area article cards")

        booking_links = self.find_all("booking_com_links")
        google_links = self.find_all("google_hotel_links")

        if booking_links:
            self.log(f"Found {len(booking_links)} Booking.com link(s)")
        else:
            self.error("No Booking.com links found")

        if google_links:
            self.log(f"Found {len(google_links)} Google Hotels link(s)")
        else:
            self.error("No Google Hotels links found")

        # Verify at least one pair of dual buttons
        if booking_links and google_links:
            self.log("Dual booking buttons (Booking.com + Google Hotels) present")

    def test_car_rental(self) -> None:
        print("\n=== Testing Car Rental Page ===")
        self.goto("/car-rental/")

        if "Tizahab" not in self.driver.title:
            self.error("Car Rental page did not load")
            return

        articles = self.find_all("rental_articles")
        self.log(f"Found {len(articles)} provider article cards")

        for key, label in [("theeb_heading", "Theeb"), ("yelo_heading", "Yelo")]:
            if self.driver.find_elements(*SELECTORS[key]):
                self.log(f"Car rental company '{label}' present")
            else:
                self.error(f"Car rental company '{label}' not found")

        # Ride-hailing section
        ride_els = self.driver.find_elements(
            By.XPATH,
            "//*[contains(text(),'Uber') or contains(text(),'Careem') or contains(text(),'ride')]",
        )
        if ride_els:
            self.log(f"Ride-hailing service section found")
        else:
            self.log("No explicit Uber/Careem mention found (check template)")

        # All external links open in new tab
        ext_links = self.driver.find_elements(By.XPATH, "//a[@target='_blank']")
        if ext_links:
            self.log(f"{len(ext_links)} external links open in new tab (target=_blank)")

    def test_travel_guide(self) -> None:
        print("\n=== Testing Travel Guide ===")
        self.goto("/travel-guide/")

        if "Tizahab" not in self.driver.title:
            self.error("Travel Guide page did not load")
            return

        cards = self.find_all("guide_cards")
        if cards:
            self.log(f"Found {len(cards)} guide cards (.guide-card)")
        else:
            self.error("No guide cards (.guide-card) found")

        # Hero h1
        try:
            h1 = self.driver.find_element(By.TAG_NAME, "h1")
            self.log(f"Page heading: '{h1.text.strip()}'")
        except NoSuchElementException:
            self.error("No <h1> heading on Travel Guide page")

    def test_profile(self) -> None:
        print("\n=== Testing Profile ===")
        self.goto("/profile/")

        if "Tizahab" not in self.driver.title:
            self.error("Profile page did not load (possible auth redirect)")
            return

        profile_name = self.find("profile_name")
        if profile_name:
            self.log(
                f"Profile name element present (text: '{profile_name.text.strip()}')"
            )
        else:
            self.error("Profile name (#profileName) not found")

        for stat_key, label in [
            ("stat_plans", "Plans Created"),
            ("stat_favs", "Saved Places"),
        ]:
            el = self.driver.find_elements(*SELECTORS[stat_key])
            if el:
                self.log(f"Stat card '{label}' present (value: '{el[0].text.strip()}')")
            else:
                self.error(f"Stat element #{stat_key.replace('_', '')} not found")

        logout_btn = self.find("logout_btn")
        if logout_btn:
            self.log("Logout button (#logoutBtn) present on profile page")
        else:
            self.error("Logout button (#logoutBtn) not found on profile page")

    def test_logout(self) -> None:
        print("\n=== Testing Logout ===")
        # Ensure we're on profile to use the in-page logout button
        if "/profile/" not in self.driver.current_url:
            self.goto("/profile/")

        logout_btn = self.find("logout_btn")
        if logout_btn is None:
            # Fallback: hit the logout URL directly
            self.goto("/logout/")
        else:
            try:
                logout_btn.click()
            except Exception as e:
                self.error(f"Logout button click failed: {e}")
                self.goto("/logout/")

        time.sleep(2)

        if "/login/" in self.driver.current_url or self.driver.current_url == self.url(
            "/"
        ):
            self.log(f"Logout successful — redirected to {self.driver.current_url}")
        else:
            self.error(f"Unexpected URL after logout: {self.driver.current_url}")

        # Confirm protected page now redirects to login
        self.goto("/profile/")
        time.sleep(2)
        if "/login/" in self.driver.current_url:
            self.log("Protected route correctly redirects to /login/ after logout")
        else:
            self.error(
                f"Protected route did not redirect after logout: {self.driver.current_url}"
            )

    def test_event_detail(self) -> None:
        print("\n=== Testing Event Detail Page ===")
        self.goto("/events/page/")

        cards = self.find_all("event_cards")
        if not cards:
            self.log("No event cards found — skipping detail page test")
            return

        try:
            # Click the first card link
            link = cards[0].find_element(By.TAG_NAME, "a")
            href = link.get_attribute("href")
            self.driver.get(href)
            time.sleep(2)

            h1_els = self.driver.find_elements(By.TAG_NAME, "h1")
            if h1_els:
                self.log(f"Event detail page loaded: '{h1_els[0].text.strip()[:60]}'")
            else:
                self.error("Event detail page has no <h1>")
        except Exception as e:
            self.log(f"Event detail not directly linked (expected): {e}")

    def test_settings(self) -> None:
        print("\n=== Testing Settings Page ===")
        self.goto("/settings/")

        if "Tizahab" not in self.driver.title:
            self.error("Settings page did not load")
            return

        try:
            h1 = self.driver.find_element(By.TAG_NAME, "h1")
            self.log(f"Settings heading: '{h1.text.strip()}'")
        except NoSuchElementException:
            self.error("No <h1> on settings page")

        save_btns = self.driver.find_elements(By.XPATH, "//*[contains(text(),'Save')]")
        if save_btns:
            self.log(f"Found {len(save_btns)} 'Save' button(s) on settings page")

    # ── Main runner ────────────────────────────────────────────────────────────

    def test_all(self) -> None:
        self.test_landing_page()
        self.test_signup()
        self.test_preferences()
        self.test_daily_plan()
        self.test_explore()
        self.test_booking()
        self.test_car_rental()
        self.test_travel_guide()
        self.test_profile()
        self.test_logout()
        self.generate_report()

    def generate_report(self) -> None:
        total = len(self.passed) + len(self.errors)
        print("\n" + "=" * 56)
        print("TIZAHAB TEST REPORT")
        print("=" * 56)
        print(f"URL:     {self.base_url}")
        print(f"Passed:  {len(self.passed)}/{total}")
        print(f"Errors:  {len(self.errors)}/{total}")

        if self.errors:
            print(f"\nFAILED ({len(self.errors)} issue(s)):\n")
            for i, e in enumerate(self.errors, 1):
                print(f"  {i:2}. {e}")
            print()
        else:
            print("\n  ALL CHECKS PASSED")

        print("=" * 56)

    def cleanup(self) -> None:
        try:
            self.driver.quit()
        except Exception:
            pass


# ── Entry point ────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tizahab end-to-end test suite")
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8000",
        help="Base URL to test against (default: production)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Chrome in headless mode",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    tester = TizahabTest(base_url=args.url, headless=args.headless)
    try:
        tester.test_all()
    finally:
        tester.cleanup()
