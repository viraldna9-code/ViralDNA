#!/usr/bin/env python3
"""
THE VIRAL DNA — YouTube Studio Uploader via Selenium (Windows-native)
Run this on Windows. No API quota cost. Uses your existing Chrome login.

Usage:
  python youtube_selenium_uploader.py upload <video_path> --title "..." --desc "..." --tags tag1,tag2 --privacy private
  python youtube_selenium_uploader.py trailer
  python youtube_selenium_uploader.py batch <folder_path>
"""

import os
import sys
import time
import json
from pathlib import Path

# ── Configuration ──
CHROME_BINARY = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CHROMEDRIVER_DIR = r"C:\Users\sudha\ViralDNA\credentials\chromedriver\chromedriver-win64\chromedriver.exe"
COOKIE_FILE = r"C:\Users\sudha\ViralDNA\credentials\youtube_cookies.json"
CHANNEL_ID = "UCkW7fqkJiaej2PeNcP4PejQ"
STUDIO_URL = "https://studio.youtube.com"

DEFAULT_TITLE = "The Viral DNA"
DEFAULT_DESC = """The Viral DNA — Telugu News. Real News. Real Voices. Built with AI.

Coverage: Andhra Pradesh News, Telangana News, Politics, Entertainment, Sports, Tech, Business, Telugu people worldwide.

No newsroom. No anchors. No agenda. Just AI delivering what matters to Telugu people everywhere.

📰 Real News. Real Voices. Built with AI.
🔔 Subscribe. One click. Every day."""

DEFAULT_TAGS = ["telugu news", "andhra pradesh", "telangana", "ai news", "viral dna", "telugu people"]


def get_driver():
    """Launch Chrome with Selenium using Windows-native Chrome."""
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options

    opts = Options()
    opts.binary_location = CHROME_BINARY

    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument(r"--user-data-dir=C:\Users\sudha\AppData\Local\Google\Chrome\User Data")
    opts.add_argument("--profile-directory=Default")

    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    # Try explicit chromedriver path first, then webdriver-manager fallback
    if os.path.exists(CHROMEDRIVER_DIR):
        service = Service(CHROMEDRIVER_DIR)
    else:
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())

    driver = webdriver.Chrome(service=service, options=opts)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    driver.implicitly_wait(15)
    return driver


def chrome_login_if_needed(driver):
    """Check if logged in to YouTube. If not, wait for manual login."""
    import selenium.webdriver.support.expected_conditions as EC
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait

    driver.get(STUDIO_URL)
    time.sleep(4)

    # If redirected to Google sign-in, we need to handle it
    if "accounts.google.com" in driver.current_url or "signin" in driver.current_url:
        print("[LOGIN] Please sign in to Google in the Chrome window...")
        print("[LOGIN] Waiting for login (max 120s)...")

        for i in range(24):
            time.sleep(5)
            if "studio.youtube.com" in driver.current_url:
                print("[LOGIN] Successfully logged in!")
                # Save cookies for next time
                _save_cookies(driver)
                return True
            print(f"  Waiting... ({(i+1)*5}s)", end="\r")

        print("\n[ERROR] Login timeout")
        return False

    print("[LOGIN] Already logged in")
    return True


def _save_cookies(driver):
    try:
        cookies = driver.get_cookies()
        os.makedirs(os.path.dirname(COOKIE_FILE), exist_ok=True)
        with open(COOKIE_FILE, "w") as f:
            json.dump(cookies, f, indent=2)
        print(f"[COOKIES] Saved {len(cookies)} cookies")
    except Exception as e:
        print(f"[COOKIES] Save failed: {e}")


def fill_and_upload(driver, video_path, title, description, tags, privacy="private"):
    """Upload and fill details for one video."""
    import selenium.webdriver.support.expected_conditions as EC
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.common.keys import Keys

    video_path = str(Path(video_path).resolve())
    if not os.path.exists(video_path):
        print(f"[ERROR] File not found: {video_path}")
        return False

    print(f"\n[UPLOAD] {os.path.basename(video_path)}")
    print(f"  Title: {title[:60]}")
    print(f"  Size: {os.path.getsize(video_path) / 1024 / 1024:.1f} MB")

    # Navigate to upload
    driver.get(f"https://studio.youtube.com/channel/{CHANNEL_ID}/videos/upload")
    time.sleep(4)

    # Find file input and upload
    file_input = WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='file'][accept*='video']"))
    )
    file_input.send_keys(video_path)
    print(f"  [FILE] Sent to browser ({os.path.getsize(video_path) // 1024 // 1024} MB)")

    # Wait for upload bar to appear and fill title/description
    print("  [UPLOAD] Uploading... (waiting for details form)")
    time.sleep(10)

    # Fill title
    try:
        title_box = WebDriverWait(driver, 60).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "div[aria-label*='title' i], #title-textarea, ytcp-social-mention-input"))
        )
        title_box.click()
        time.sleep(0.5)
        title_box.send_keys(title)
        print(f"  [TITLE] Set")
    except Exception as e:
        print(f"  [WARN] Title field issue: {e}")

    time.sleep(1)

    # Fill description
    try:
        desc_box = WebDriverWait(driver, 30).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "div[aria-label*='description' i], #description-textarea .ytcp-form-input-container .ytcp-form-input"))
        )
        desc_box.click()
        time.sleep(0.5)
        desc_box.send_keys(description)
        print(f"  [DESC] Set ({len(description)} chars)")
    except Exception as e:
        print(f"  [WARN] Description field issue: {e}")

    time.sleep(1)

    # Fill tags
    if tags:
        try:
            tags_container = driver.find_element(By.CSS_SELECTOR, "ytcp-form-input-container#tags-container input, input[aria-label*='tag' i], #tags-input input")
            tags_container.click()
            time.sleep(0.3)
            tags_container.send_keys(", ".join(tags))
            print(f"  [TAGS] Set ({len(tags)} tags)")
        except Exception as e:
            print(f"  [WARN] Tags field issue: {e}")

    time.sleep(2)

    # Click through "Next" buttons (YouTube Studio has multiple pages)
    next_selectors = [
        "ytcp-button#next-button",
        "yt-button-shape button:has(span:contains('Next'))",
        "button[aria-label='Next']",
        ".next-button",
    ]
    for _ in range(3):  # YouTube has up to 3 "Next" pages
        clicked = False
        for sel in next_selectors:
            try:
                btn = driver.find_element(By.CSS_SELECTOR, sel)
                if btn.is_displayed() and btn.is_enabled():
                    btn.click()
                    clicked = True
                    print(f"  [NEXT] Clicked")
                    time.sleep(2)
                    break
            except Exception:
                continue
        if not clicked:
            break

    # Select privacy
    if privacy != "private":
        try:
            priv_btn = driver.find_element(By.CSS_SELECTOR, f"tp-yt-paper-radio-button[name*='{privacy}' i], ytcp-visibility-selector [value='{privacy}']")
            priv_btn.click()
            print(f"  [PRIVACY] Set to {privacy}")
        except Exception as e:
            print(f"  [WARN] Privacy: defaulting to private ({e})")

    time.sleep(2)

    # Click Save/Publish/Done
    save_selectors = [
        "ytcp-button#done-button",
        "yt-button-shape button:has(span:contains('Save'))",
        "yt-button-shape button:has(span:contains('Publish'))",
        "button[aria-label='Save']",
        "button[aria-label='Publish']",
        ".done-button",
        "#save-button",
    ]
    saved = False
    for sel in save_selectors:
        try:
            btn = driver.find_element(By.CSS_SELECTOR, sel)
            if btn.is_displayed() and btn.is_enabled():
                btn.click()
                saved = True
                print(f"  [SAVE] Clicked!")
                time.sleep(3)
                break
        except Exception:
            continue

    if not saved:
        print("  [WARN] Could not find Save/Publish button. Please click manually.")
        input("  Press Enter after clicking Save/Publish...")

    _save_cookies(driver)
    print(f"  [DONE] Uploaded: {driver.current_url}")
    return True


def upload_trailer():
    """Upload channel trailer."""
    driver = get_driver()
    try:
        if not chrome_login_if_needed(driver):
            return

        trailer = r"C:\Users\sudha\ViralDNA\videos\trailer\v7\trailer_v7_final.mp4"
        title = "The Viral DNA — Channel Trailer | Real News. Real Voices. Built with AI."
        desc = DEFAULT_DESC + "\n\nReal News. Real Voices. Built with AI.\nSubscribe. One click. Every day."
        tags = DEFAULT_TAGS + ["channel trailer"]
        fill_and_upload(driver, trailer, title, desc, tags, privacy="private")

    finally:
        driver.quit()


def upload_video(video_path, title=None, desc=None, tags=None, privacy="private"):
    """Upload a single video."""
    driver = get_driver()
    try:
        if not chrome_login_if_needed(driver):
            return
        title = title or DEFAULT_TITLE
        desc = desc or DEFAULT_DESC
        tags = tags or DEFAULT_TAGS
        fill_and_upload(driver, video_path, title, desc, tags, privacy)
    finally:
        driver.quit()


def batch_upload(folder_path, privacy="private"):
    """Upload all MP4 files in a folder."""
    folder = Path(folder_path)
    mp4s = sorted(folder.glob("*.mp4"))
    if not mp4s:
        print(f"No MP4 files in {folder}")
        return

    print(f"[BATCH] Found {len(mp4s)} videos")
    driver = get_driver()
    try:
        if not chrome_login_if_needed(driver):
            return
        for i, mp4 in enumerate(mp4s, 1):
            print(f"\n{'='*50}")
            print(f"[BATCH {i}/{len(mp4s)}] {mp4.name}")
            tags_str = mp4.stem.replace("_", " ").replace("-", " ")
            title = f"The Viral DNA — {mp4.stem[:80]}"
            fill_and_upload(driver, str(mp4), title, DEFAULT_DESC, DEFAULT_TAGS, privacy)
            if i < len(mp4s):
                print(f"  [PAUSE] 10s before next upload...")
                time.sleep(10)
    finally:
        driver.quit()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "trailer":
        upload_trailer()

    elif cmd == "upload":
        if len(sys.argv) < 3:
            print("Usage: python youtube_selenium_uploader.py upload <video_path> [--title ...] [--desc ...] --tags t1,t2 [--privacy private]")
            sys.exit(1)
        video_path = sys.argv[2]
        title = None
        desc = None
        tags = None
        privacy = "private"
        i = 3
        while i < len(sys.argv):
            if sys.argv[i] == "--title" and i+1 < len(sys.argv):
                title = sys.argv[i+1]; i += 2
            elif sys.argv[i] == "--desc" and i+1 < len(sys.argv):
                desc = sys.argv[i+1]; i += 2
            elif sys.argv[i] == "--tags" and i+1 < len(sys.argv):
                tags = [t.strip() for t in sys.argv[i+1].split(",")]; i += 2
            elif sys.argv[i] == "--privacy" and i+1 < len(sys.argv):
                privacy = sys.argv[i+1]; i += 2
            else:
                i += 1
        upload_video(video_path, title, desc, tags, privacy)

    elif cmd == "batch":
        if len(sys.argv) < 3:
            print("Usage: python youtube_selenium_uploader.py batch <folder_path> [--privacy private]")
            sys.exit(1)
        folder = sys.argv[2]
        privacy = "private"
        if "--privacy" in sys.argv:
            idx = sys.argv.index("--privacy")
            if idx+1 < len(sys.argv):
                privacy = sys.argv[idx+1]
        batch_upload(folder, privacy)

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
