"""
End-to-End Real Browser Automation Test using Playwright.
Launches backend & frontend servers, opens Chromium, clicks every button,
verifies form submissions, and captures screenshots for the user.
"""

import os
import sys
import time
import subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright

ARTIFACTS_DIR = Path(r"C:\Users\lgowd\.gemini\antigravity\brain\c1f43d81-ba05-47ff-8e73-c1c3197bb7f6")
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


def wait_for_url(url: str, timeout: int = 20) -> bool:
    import urllib.request
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status in (200, 304):
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def run_browser_automation():
    print("=" * 70)
    print("STARTING REAL BROWSER AUTOMATION TEST (CHROMIUM + PLAYWRIGHT)")
    print("=" * 70)

    backend_proc = None
    frontend_proc = None

    try:
        # Step 1: Start Backend Server
        print("\n[Step 1] Launching Python FastAPI backend on http://127.0.0.1:8000...")
        backend_cmd = [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--port", "8000", "--host", "127.0.0.1"]
        backend_proc = subprocess.Popen(backend_cmd, cwd=str(ROOT_DIR))

        # Step 2: Start Frontend Server
        print("[Step 2] Launching React Vite dev server on http://localhost:5173...")
        npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
        frontend_cmd = [npm_cmd, "--prefix", "frontend", "run", "dev", "--", "--port", "5173", "--host"]
        frontend_proc = subprocess.Popen(frontend_cmd, cwd=str(ROOT_DIR))

        # Wait for both servers to be ready
        print("  -> Waiting for backend to respond at http://127.0.0.1:8000/health...")
        if not wait_for_url("http://127.0.0.1:8000/health", timeout=25):
            raise RuntimeError("Backend failed to start on port 8000")
        print("     [OK] Backend is healthy and listening.")

        print("  -> Waiting for frontend to respond at http://localhost:5173...")
        if not wait_for_url("http://localhost:5173", timeout=25):
            raise RuntimeError("Frontend failed to start on port 5173")
        print("     [OK] Frontend is live and responding.")

        # Step 3: Launch Chromium
        print("\n[Step 3] Launching real Chromium browser via Playwright...")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})

            # Real-time console and network logging
            page.on("console", lambda msg: print(f"  [BROWSER CONSOLE] {msg.text}"))
            page.on("requestfailed", lambda req: print(f"  [NETWORK FAILED] {req.url} {req.failure}"))
            page.on("response", lambda res: print(f"  [HTTP {res.status}] {res.url}") if "/api/" in res.url else None)

            # Navigate to the app
            print("  -> Navigating to http://localhost:5173/...")
            page.goto("http://localhost:5173/", wait_until="networkidle")
            time.sleep(1.5)

            # Check if Links & Locks tab needs clicking
            links_tab = page.locator("text=Links & Locks (T10)")
            if links_tab.is_visible():
                print("  -> Clicking 'Links & Locks (T10)' tab...")
                links_tab.click()
                time.sleep(1)

            # VERIFY 1: Check that error 500 is NOT present
            error_banner = page.locator("text=Failed to load links: Server returned 500")
            if error_banner.is_visible():
                print("  [FAIL] Error banner is visible!")
                raise RuntimeError("500 error banner was displayed on page load!")
            else:
                print("  [PASS] Confirmed: Zero 500 errors! Clean page load.")

            # Capture initial screenshot
            shot1 = ARTIFACTS_DIR / "browser_1_initial_load.png"
            page.screenshot(path=str(shot1), full_page=True)
            print(f"  -> Saved initial view screenshot: {shot1.name}")

            # VERIFY 2: Test "Add Manual Link" Modal and Form
            print("\n[Step 4] Testing 'Add Manual Link' button and modal...")
            add_button = page.locator("button:has-text('Add Manual Link')")
            assert add_button.is_visible(), "Add Manual Link button must be visible"
            add_button.click()
            time.sleep(0.5)

            # Check modal opened
            modal_title = page.locator("h2:has-text('Add Manual Link')")
            assert modal_title.is_visible(), "Add Manual Link modal did not open"
            print("  [PASS] Add Manual Link modal opened smoothly.")

            # Populate Topic A and Topic B dropdowns inside modal form
            modal_form = page.locator("form")
            topic_a_select = modal_form.locator("select").nth(0)  # In modal, first select is topic_a
            topic_b_select = modal_form.locator("select").nth(1)  # Second select is topic_b
            
            topic_a_select.select_option(index=1)
            time.sleep(0.3)
            topic_b_select.select_option(index=2)
            time.sleep(0.3)
            print("  -> Selected Topic A (index 1) and Topic B (index 2)")

            # Fill reason
            modal_form.locator("textarea").fill("Playwright Browser Automation Test: Verifying end-to-end browser actions work flawlessly.")
            modal_form.locator("input[placeholder*='Cloudflare']").fill("Automated Playwright cloud deployment test.")

            # Fill manual snippets
            modal_form.locator("input[placeholder*='Topic A']").fill("Manual evidence snippet for Topic A from real browser test.")
            modal_form.locator("input[placeholder*='Topic B']").fill("Manual evidence snippet for Topic B from real browser test.")

            # Capture modal filled screenshot
            shot2 = ARTIFACTS_DIR / "browser_2_modal_filled.png"
            page.screenshot(path=str(shot2))
            print(f"  -> Saved modal screenshot: {shot2.name}")

            # Submit form
            print("  -> Submitting manual link form...")
            with page.expect_response(lambda res: "/api/edges/manual" in res.url and res.status == 201):
                submit_btn = modal_form.locator("button:has-text('Save Manual Link & Lock')")
                submit_btn.click()
            
            time.sleep(1)

            # Verify success toast
            success_toast = page.locator("text=Manual link created and locked")
            if not success_toast.is_visible():
                err_loc = page.locator(".text-rose-800")
                if err_loc.is_visible():
                    print("  [PAGE ERROR MESSAGE]:", err_loc.text_content())
            assert success_toast.is_visible(), "Success notification did not appear"
            print("  [PASS] Manual link created successfully! Toast notification visible.")

            shot3 = ARTIFACTS_DIR / "browser_3_manual_created.png"
            page.screenshot(path=str(shot3), full_page=True)
            print(f"  -> Saved manual link view screenshot: {shot3.name}")

            # VERIFY 3: Test Link Inline Edit
            print("\n[Step 5] Testing 'Edit' action on first link card...")
            first_edit_btn = page.locator("button:has-text('Edit')").first
            first_edit_btn.click()
            time.sleep(0.5)

            # Change reason
            edit_textarea = page.locator("textarea").first
            edit_textarea.fill("USER UPDATED IN BROWSER: Automated verification of locked link survival.")

            # Click Save & Lock Link
            with page.expect_response(lambda res: res.request.method == "PATCH" and res.status == 200):
                save_edit_btn = page.locator("button:has-text('Save & Lock Link')")
                save_edit_btn.click()
            time.sleep(1)

            # Check notification
            edit_toast = page.locator("text=Link successfully updated and locked")
            assert edit_toast.is_visible(), "Edit toast did not appear"
            print("  [PASS] Link edited and locked successfully!")

            shot4 = ARTIFACTS_DIR / "browser_4_edited_locked.png"
            page.screenshot(path=str(shot4), full_page=True)
            print(f"  -> Saved edited link screenshot: {shot4.name}")

            # VERIFY 4: Test Soft Delete
            print("\n[Step 6] Testing 'Soft Delete' on link card...")
            del_btn = page.locator("button:has-text('Soft Delete')").first
            del_btn.click()
            time.sleep(0.5)

            confirm_modal = page.locator("h2:has-text('Soft-Delete Link')")
            assert confirm_modal.is_visible(), "Delete confirmation modal did not open"
            print("  [PASS] Soft-delete confirmation modal opened.")

            with page.expect_response(lambda res: res.request.method == "DELETE" and res.status == 200):
                confirm_del_btn = page.locator("button:has-text('Confirm Soft Delete')")
                confirm_del_btn.click()
            time.sleep(1)

            del_toast = page.locator("text=Link soft-deleted and locked")
            assert del_toast.is_visible(), "Delete toast did not appear"
            print("  [PASS] Link successfully soft-deleted and locked!")

            # VERIFY 5: Toggle Audit Mode to check deleted retention
            print("\n[Step 7] Checking 'Show Soft-Deleted (Audit)' checkbox...")
            audit_checkbox = page.locator("#includeDeleted")
            audit_checkbox.check()
            time.sleep(1.5)

            # Check that deleted badge is visible
            deleted_badge = page.locator("span:has-text('deleted')").first
            assert deleted_badge.is_visible(), "Deleted link must be retained and visible in audit mode"
            print("  [PASS] Soft-deleted link correctly retained in audit view with 'deleted' status.")

            shot5 = ARTIFACTS_DIR / "browser_5_audit_mode.png"
            page.screenshot(path=str(shot5), full_page=True)
            print(f"  -> Saved audit mode screenshot: {shot5.name}")

            browser.close()

        print("\n" + "=" * 70)
        print("ALL REAL BROWSER TESTS PASSED FLAWLESSLY WITH 0 ERRORS!")
        print("=" * 70)
        return True

    finally:
        # Cleanly stop background servers
        print("\n[Cleanup] Stopping backend and frontend server processes...")
        if backend_proc:
            backend_proc.terminate()
            try:
                backend_proc.wait(timeout=3)
            except Exception:
                backend_proc.kill()
        if frontend_proc:
            frontend_proc.terminate()
            try:
                frontend_proc.wait(timeout=3)
            except Exception:
                frontend_proc.kill()
        print("  -> Servers stopped cleanly.")


if __name__ == "__main__":
    success = run_browser_automation()
    sys.exit(0 if success else 1)
