"""End-to-end browser test against the real docker-compose stack.

Walks the full product path with two distinct users in separate browser
contexts (separate localStorage, so genuinely separate sessions):

    register -> verify OTP -> login -> report an item
      -> second user finds it via search -> files a claim
      -> first user approves -> first user closes -> detail shows 'closed'

Nothing is mocked. Every step talks to the running API.

OTP handling
------------
OTPs are NOT faked. `otp_tokens.code_hash` is a bcrypt hash, so the code cannot
be read back out of the database. The real dev-mode retrieval path is the API
itself: with MAIL_ENABLED=false the register/reset endpoints return the live
code as `otp_debug` instead of emailing it. This test captures that value off
the actual HTTP response via a Playwright response listener, and types it into
the form -- the same code the server will verify against.

Usage:
    docker compose up -d
    python scripts/e2e_test.py [base_url]

Exit code is non-zero if any ASSERTION fails (not merely if a page loaded).
"""
from __future__ import annotations

import re
import sys
import uuid
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
SHOTS = Path(__file__).resolve().parent / "e2e_screenshots"
SHOTS.mkdir(parents=True, exist_ok=True)

PASSWORD = "correct-horse-battery"
_step = 0
_results: list[tuple[str, bool, str]] = []
_js_errors: list[str] = []


def shot(page: Page, name: str) -> None:
    global _step
    _step += 1
    page.screenshot(path=str(SHOTS / f"{_step:02d}-{name}.png"), full_page=True)


def assert_that(label: str, condition: bool, detail: str = "") -> bool:
    """Record a real assertion. A screenshot proves a page rendered; this
    proves the flow actually did what it claims."""
    _results.append((label, bool(condition), detail))
    mark = "ok  " if condition else "FAIL"
    print(f"  [{mark}] {label}" + (f"   -> {detail}" if detail and not condition else ""))
    return bool(condition)


def otp_matches_database(email: str, otp: str) -> bool | None:
    """Cross-check the captured OTP against the hash PostgreSQL actually stored.

    otp_tokens.code_hash is a bcrypt hash, so the code cannot be read out of the
    database -- but it CAN be verified against. If this passes, the captured
    value is provably the real code the server will accept, not a fabrication.
    Returns None if the database is not reachable from here.
    """
    import subprocess

    sql = (
        "SELECT t.code_hash FROM otp_tokens t JOIN users u ON u.id = t.user_id "
        f"WHERE u.email = '{email}' AND t.purpose = 'registration' "
        "ORDER BY t.created_at DESC LIMIT 1"
    )
    try:
        out = subprocess.run(
            ["docker", "compose", "exec", "-T", "db", "psql", "-U", "lostfound",
             "-d", "lostfound", "-tAc", sql],
            capture_output=True, text=True, timeout=30,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        digest = out.stdout.strip()
        if not digest:
            return None
        import bcrypt

        return bcrypt.checkpw(otp.encode(), digest.encode())
    except Exception:
        return None


def register_verify_login(page: Page, tag: str, first: str) -> str:
    """Full signup using a REAL OTP captured from the API response."""
    email = f"e2e-{first.lower()}-{tag}@campus.edu"

    page.goto(f"{BASE}/app/register.html")
    for sel, val in [
        ("reg-first-name", first), ("reg-last-name", "Endtoend"),
        ("reg-email", email), ("reg-password", PASSWORD),
        ("reg-roll", f"R{first[:2].upper()}{tag[:6]}"), ("reg-batch", "2026"),
    ]:
        page.fill(f'[data-testid="{sel}"]', val)
    shot(page, f"register-{first.lower()}")

    # Capture the live registration response body.
    #
    # Neither page.on("response") nor expect_response can read this body: the
    # page navigates to verify.html the instant the request resolves, and
    # Chromium discards bodies of navigated-away responses. Intercepting the
    # route lets us read it *before* the page's JS ever sees it.
    captured: dict[str, str] = {}

    def intercept(route):
        response = route.fetch()
        try:
            body = response.json()
            if body.get("otp_debug"):
                captured["otp"] = body["otp_debug"]
        except Exception:
            pass
        route.fulfill(response=response)

    page.route("**/auth/register", intercept)
    page.click('[data-testid="reg-submit"]')
    page.wait_for_url(re.compile(r"verify\.html"), timeout=15000)
    page.unroute("**/auth/register", intercept)
    api_otp = captured.get("otp")
    otp_in_form = page.input_value('[data-testid="verify-otp"]')

    assert_that(
        f"{first}: real OTP issued by the API (not fabricated)",
        bool(api_otp) and re.fullmatch(r"\d{6}", api_otp or "") is not None,
        f"otp_debug={api_otp!r}",
    )
    assert_that(
        f"{first}: OTP on the form matches the one the API issued",
        otp_in_form == api_otp,
        f"form={otp_in_form!r} api={api_otp!r}",
    )
    print(f"        OTP issued by API for {first}: {api_otp}")

    verified = otp_matches_database(email, api_otp or "")
    if verified is None:
        print("        (database cross-check skipped: db not reachable from here)")
    else:
        assert_that(
            f"{first}: OTP verifies against the bcrypt hash stored in PostgreSQL",
            verified,
        )
    shot(page, f"verify-otp-{first.lower()}")

    page.click('[data-testid="verify-submit"]')
    page.wait_for_url(re.compile(r"login\.html"), timeout=15000)
    assert_that(
        f"{first}: verification succeeded (redirected with confirmation)",
        "verified" in (page.text_content("[data-notice]") or "").lower(),
    )

    page.fill('[data-testid="login-email"]', email)
    page.fill('[data-testid="login-password"]', PASSWORD)
    shot(page, f"login-{first.lower()}")
    page.click('[data-testid="login-submit"]')
    page.wait_for_url(re.compile(r"index\.html"), timeout=15000)
    token = page.evaluate("localStorage.getItem('lf_token')")
    assert_that(f"{first}: logged in, JWT stored", bool(token) and token.count(".") == 2)
    return email


def main() -> int:
    tag = uuid.uuid4().hex[:8]
    item_name = f"Charcoal Rain Jacket {tag}"
    item_desc = f"Zip broken at the base, initials JM inside collar, ref {tag}"

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        owner_ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        finder_ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        owner, finder = owner_ctx.new_page(), finder_ctx.new_page()
        for p in (owner, finder):
            p.on("pageerror", lambda e: _js_errors.append(str(e)))

        print("STEP 1-3  owner: register -> verify OTP -> login")
        register_verify_login(owner, tag, "Olive")

        print("\nSTEP 4    owner: report an item")
        owner.goto(f"{BASE}/app/report.html")
        owner.fill('[data-testid="report-name"]', item_name)
        owner.fill('[data-testid="report-description"]', item_desc)
        owner.select_option('[data-testid="report-kind"]', "found")
        owner.fill('[data-testid="report-date"]', "2026-08-10")
        owner.click("details summary")
        owner.fill('[data-testid="new-location-name"]', f"Sports Complex {tag}")
        owner.fill('[data-testid="new-location-building"]', "Gate 2")
        owner.click("[data-add-location]")
        owner.wait_for_timeout(900)
        assert_that("location created and selected",
                    bool(owner.input_value('[data-testid="report-location"]')))
        shot(owner, "report-form")
        owner.click('[data-testid="report-submit"]')
        owner.wait_for_url(re.compile(r"item\.html\?id=\d+"), timeout=15000)
        item_id = re.search(r"id=(\d+)", owner.url).group(1)
        owner.wait_for_selector('[data-testid="item-name"]:not(:empty)', timeout=15000)
        assert_that("item created with the submitted name",
                    owner.text_content('[data-testid="item-name"]').strip() == item_name)
        assert_that("new item starts at 'reported'",
                    "reported" in owner.text_content('[data-testid="item-status"]').lower(),
                    owner.text_content('[data-testid="item-status"]'))
        shot(owner, "item-reported")

        print("\nSTEP 5-6  second user: register/login, then find it via search")
        register_verify_login(finder, tag, "Fintan")
        finder.goto(f"{BASE}/app/index.html")
        finder.fill('[data-testid="search-q"]', f"initials JM inside collar, ref {tag}")
        finder.click('[data-testid="search-submit"]')
        finder.wait_for_timeout(1500)
        cards = finder.locator('[data-testid="item-card"]')
        assert_that("search by description returned exactly the item", cards.count() == 1,
                    f"count={cards.count()}")
        assert_that("the search hit is the right item",
                    cards.first.get_attribute("data-item-id") == item_id,
                    f"got={cards.first.get_attribute('data-item-id')} want={item_id}")
        shot(finder, "search-results")

        print("\nSTEP 7    second user: file a claim")
        cards.first.click()
        finder.wait_for_url(re.compile(r"item\.html\?id="), timeout=15000)
        finder.wait_for_selector('[data-testid="claim-evidence"]', timeout=15000)
        url_before = finder.url
        finder.fill('[data-testid="claim-evidence"]',
                    "The initials JM are mine and the zip broke last term; I have a repair receipt.")
        shot(finder, "claim-form")
        finder.click('[data-testid="claim-submit"]')
        finder.wait_for_timeout(2000)
        assert_that("filing a claim advanced the item to 'matched'",
                    "matched" in finder.text_content('[data-testid="item-status"]').lower(),
                    finder.text_content('[data-testid="item-status"]'))
        assert_that("claim filed without a page navigation", finder.url == url_before)
        shot(finder, "item-matched")

        print("\nSTEP 8    owner: sees and approves the claim")
        owner.goto(f"{BASE}/app/claims.html")
        owner.wait_for_timeout(2200)
        incoming = owner.text_content('[data-testid="incoming-claims"]') or ""
        assert_that("owner sees the incoming claim", "Fintan Endtoend" in incoming,
                    repr(incoming[:120]))
        assert_that("claim is pending", "pending" in incoming.lower())
        shot(owner, "claims-inbox")

        owner.goto(f"{BASE}/app/item.html?id={item_id}")
        owner.wait_for_selector('[data-testid="claim-row"]', timeout=15000)
        approve = owner.locator('[data-testid^="approve-"]').first
        assert_that("approve control available to the reporter", approve.count() == 1)
        url_before = owner.url
        approve.click()
        owner.wait_for_timeout(2200)
        assert_that("approval advanced the item to 'claimed'",
                    "claimed" in owner.text_content('[data-testid="item-status"]').lower(),
                    owner.text_content('[data-testid="item-status"]'))
        assert_that("approval happened without a navigation", owner.url == url_before)
        assert_that("claim row shows 'approved'",
                    "approved" in (owner.text_content("[data-item-claims]") or "").lower())
        shot(owner, "item-claimed")

        print("\nSTEP 9    owner: close the item")
        # Approval reaches 'claimed'; 'closed' is a separate, explicit transition.
        owner.wait_for_selector('[data-testid="transition-closed"]', timeout=15000)
        owner.click('[data-testid="transition-closed"]')
        owner.wait_for_timeout(2000)
        assert_that("item detail shows status 'closed'",
                    "closed" in owner.text_content('[data-testid="item-status"]').lower(),
                    owner.text_content('[data-testid="item-status"]'))
        assert_that("closed is terminal: no transitions offered",
                    owner.locator("[data-transition-buttons] button").count() == 0)
        events = owner.locator('[data-testid="item-history"] li')
        assert_that("full lifecycle recorded (4 events)", events.count() == 4,
                    f"count={events.count()}")
        history = (owner.text_content('[data-testid="item-history"]') or "").lower()
        for state in ("reported", "matched", "claimed", "closed"):
            assert_that(f"history contains '{state}'", state in history)
        shot(owner, "item-closed")

        print("\nSTEP 10   independent confirmation via a fresh page load")
        checker = browser.new_context().new_page()
        checker.goto(f"{BASE}/app/item.html?id={item_id}")
        checker.wait_for_selector('[data-testid="item-status"]', timeout=15000)
        checker.wait_for_timeout(900)
        assert_that("logged-out visitor also sees 'closed'",
                    "closed" in checker.text_content('[data-testid="item-status"]').lower(),
                    checker.text_content('[data-testid="item-status"]'))
        assert_that("closed item offers no claim form",
                    checker.locator("[data-claim-panel]").is_hidden())
        shot(checker, "final-verification")

        assert_that("no uncaught JavaScript errors in any page", not _js_errors,
                    str(_js_errors[:3]))
        browser.close()

    passed = sum(1 for _, ok, _ in _results if ok)
    failed = [(l, d) for l, ok, d in _results if not ok]
    print("\n" + "=" * 66)
    print(f"ASSERTIONS: {passed}/{len(_results)} passed")
    print(f"SCREENSHOTS: {_step} written to {SHOTS}")
    if failed:
        print(f"\n{len(failed)} ASSERTION(S) FAILED -- the flow did NOT work:")
        for label, detail in failed:
            print(f"  - {label}" + (f"   [{detail}]" if detail else ""))
        return 1
    print("\nALL ASSERTIONS PASSED: full lifecycle verified end to end.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
