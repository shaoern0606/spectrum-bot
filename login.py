import time
import sys
import logging
from playwright.sync_api import sync_playwright
from pathlib import Path
import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def _is_enter_pressed() -> bool:
    """Non-blocking check for Enter keypress on both Windows and Unix."""
    try:
        if sys.platform == "win32":
            import msvcrt
            if msvcrt.kbhit():
                key = msvcrt.getch()
                return key in (b"\r", b"\n")
            return False
        else:
            import select
            if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                sys.stdin.readline()
                return True
            return False
    except Exception:
        return False

def interactive_login():
    """
    Launches a visible browser window allowing the user to log in via UM Microsoft 365 SSO / 2FA.
    Saves session cookies to auth_state.json once login succeeds.
    """
    print("\n" + "="*60)
    print("🚀 SPeCTRUM Interactive Login Wizard")
    print("="*60)
    print("1. A Chromium browser window will open shortly.")
    print("2. Enter your SiswaMail credentials and approve the Microsoft 2FA prompt.")
    print("3. Once you reach your SPeCTRUM Dashboard, the script will automatically save your session!")
    print("="*60 + "\n")

    with sync_playwright() as p:
        # Launch visible browser
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        target_login_url = f"{config.SPECTRUM_BASE_URL}/login/index.php"
        logger.info(f"Navigating to SPeCTRUM login page: {target_login_url}")
        try:
            page.goto(target_login_url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            logger.warning(f"Navigation error: {e}. Please navigate manually in the opened browser.")

        print("\n" + "-"*50)
        print("⏳ Browser opened! Please log in to your UM account in the window.")
        print("💡 Once login is complete and you see your course dashboard, it will auto-detect.")
        print("💡 You can also return to this terminal and press [Enter] anytime to save immediately!")
        print("-" * 50 + "\n")

        # Poll every 2 seconds for up to 10 minutes (600 seconds)
        max_wait = 600
        start_time = time.time()
        logged_in = False

        while time.time() - start_time < max_wait:
            # 1. Check if user pressed Enter in terminal
            if _is_enter_pressed():
                logger.info("Received manual Enter key from user. Saving session credentials...")
                logged_in = True
                break

            current_url = page.url.lower()

            # 2. Check for confirmed login state in Moodle
            try:
                is_on_login_page = ("login" in current_url) or ("microsoftonline" in current_url)
                has_logout_button = page.locator("a[href*='login/logout.php']").count() > 0
                is_body_loggedin = page.locator("body.loggedin").count() > 0

                if not is_on_login_page and (has_logout_button or is_body_loggedin):
                    logger.info("Logout button & logged-in state detected. Authentication successful!")
                    logged_in = True
                    break
            except Exception:
                pass

            time.sleep(2)

        if logged_in:
            logger.info("Successfully reached SPeCTRUM dashboard!")
            time.sleep(2)
            context.storage_state(path=str(config.AUTH_STATE_FILE))
            print("\n" + "="*60)
            print("✅ Login successful! Session state saved securely to:")
            print(f"   {config.AUTH_STATE_FILE}")
            print("="*60 + "\n")
        else:
            print("\n⚠️ Login timed out or was not auto-detected.")
            save_anyway = input("Have you finished logging in inside the browser? (y/n): ").strip().lower()
            if save_anyway == 'y':
                context.storage_state(path=str(config.AUTH_STATE_FILE))
                print(f"✅ Credentials saved to {config.AUTH_STATE_FILE}")
            else:
                print("❌ Session was not saved. Please try running login again later.")

        browser.close()

def verify_or_renew_session() -> bool:
    """
    Attempts to verify and silently renew the SPeCTRUM session using existing auth_state.json.
    Returns True if session is active or renewed without user interaction.
    Returns False if full interactive login with password is required.
    """
    if not config.AUTH_STATE_FILE.exists():
        return False
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                storage_state=str(config.AUTH_STATE_FILE),
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            page.goto(f"{config.SPECTRUM_BASE_URL}/login/index.php", wait_until="networkidle", timeout=30000)
            has_logout = page.locator("a[href*='login/logout.php']").count() > 0
            is_body_loggedin = page.locator("body.loggedin").count() > 0
            current_url = page.url.lower()

            if not ("login" in current_url or "microsoftonline" in current_url) and (has_logout or is_body_loggedin):
                context.storage_state(path=str(config.AUTH_STATE_FILE))
                browser.close()
                return True
            browser.close()
            return False
    except Exception as e:
        logger.warning(f"Silent session renewal attempt failed: {e}")
        return False

if __name__ == "__main__":
    interactive_login()
