import sys
from playwright.sync_api import sync_playwright

def check():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            res = page.goto("http://localhost:5173", timeout=5000)
            print("Frontend status:", res.status if res else "None")
        except Exception as e:
            print("Frontend not responding:", e)

        try:
            res2 = page.goto("http://localhost:8000/health", timeout=5000)
            print("Backend status:", res2.status if res2 else "None")
        except Exception as e:
            print("Backend not responding:", e)
        browser.close()

if __name__ == "__main__":
    check()

