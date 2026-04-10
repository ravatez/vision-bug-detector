import os
from pathlib import Path
from playwright.sync_api import sync_playwright

#Base Directories
BASE_DIR = Path(__file__).resolve().parent.parent
SCREENSHOR_DIR = BASE_DIR / "data" / "screenshots"

def create_test_folder(test_name: str):
    path = SCREENSHOR_DIR / test_name
    path.mkdir(parents=True, exist_ok=True)
    return path

def capture_screenshot(page, output_path: Path):
    page.screenshot(path=str(output_path), full_page=True)

def run_capture(test_name: str, url: str):
    test_dir = create_test_folder(test_name)

    baseline_path = test_dir / "baseline.png"
    current_path = test_dir / "current.png" 

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        #Capture Baseline
        print(f"[INFO] Capturing Baseline for {test_name}")
        page.goto(url)
        page.wait_for_load_state("networkidle")
        capture_screenshot(page, baseline_path)
        
        #Simulate UI Change (Temporary for Testing)
        page.evaluate("""
                document.body.style.backgroundColor = 'red';
                """)

        #Capture Current
        print(f"[INFO] Capturing Current for {test_name}")
        capture_screenshot(page, current_path)

        browser.close()

        print(f"[SUCCESS] Screenshots saved in {test_dir}")


if __name__ == "__main__":
    run_capture("login_test", "https://example.com")