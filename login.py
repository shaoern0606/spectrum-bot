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

def remote_telegram_login(chat_id: str, email: str = "") -> bool:
    """
    Performs remote passwordless QR login via Telegram.
    1. Attempts silent renewal first using existing tokens.
    2. If needed, navigates to Microsoft SSO, enters SiswaMail, captures the QR code screenshot.
    3. Sends the QR photo to Telegram and waits up to 3 minutes for user to approve on MS Authenticator.
    4. Automatically saves auth_state.json upon successful login.
    """
    import html
    import notifier

    # 1. First attempt silent renewal if auth_state already exists
    if verify_or_renew_session():
        notifier.send_telegram_message(
            "✅ <b>【SPeCTRUM Session Active】</b>\n\n"
            "Your session was automatically verified and renewed!\n"
            "No QR code scan was needed. Background monitoring is running smoothly.",
            chat_id=chat_id
        )
        return True

    target_email = email.strip() or config.SISWA_EMAIL.strip()
    if not target_email:
        notifier.send_telegram_message(
            "💡 <b>【SPeCTRUM Passwordless QR Login】</b>\n\n"
            "To generate your login QR code, please provide your SiswaMail address:\n\n"
            "👉 <code>/login s21xxxxx@siswa.um.edu.my</code>\n\n"
            "<i>Tip: You can also set <code>SISWA_EMAIL=s21xxxxx@siswa.um.edu.my</code> in your <code>.env</code> file to log in with just <code>/login</code>!</i>",
            chat_id=chat_id
        )
        return False

    notifier.send_telegram_message(
        "🔄 <b>【Generating Sign-In QR Code】</b>\n\n"
        f"Connecting to UM SPeCTRUM for <code>{html.escape(target_email)}</code>...\n"
        "A login QR code will be sent here shortly. Please open your phone's <b>Microsoft Authenticator</b> app.",
        chat_id=chat_id
    )

    temp_qr_path = config.BASE_DIR / f"login_qr_{chat_id}.png"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            try:
                page.goto(f"{config.SPECTRUM_BASE_URL}/login/index.php", wait_until="domcontentloaded", timeout=35000)
            except Exception:
                pass

            # If still on Moodle login page, trigger Microsoft SSO
            curr = page.url.lower()
            if "login/index.php" in curr or "spectrum.um.edu.my" in curr:
                for sel in [
                    "a[href*='auth/oidc']",
                    "a[href*='microsoft']",
                    "a[href*='oauth2']",
                    ".login-identityprovider-btn",
                    "a.btn-secondary",
                    "a.btn-primary"
                ]:
                    try:
                        if page.locator(sel).count() > 0 and page.locator(sel).first.is_visible():
                            page.locator(sel).first.click()
                            page.wait_for_timeout(3000)
                            break
                    except Exception:
                        pass

            # Wait for Microsoft email field
            try:
                page.wait_for_selector('input[type="email"], input[name="loginfmt"]', timeout=15000)
            except Exception:
                pass

            email_input = page.locator('input[type="email"], input[name="loginfmt"]')
            if email_input.count() > 0 and email_input.first.is_visible():
                email_input.first.fill(target_email)
                page.wait_for_timeout(500)
                submit_btn = page.locator('button[type="submit"], input[type="submit"], #idSIButton9')
                if submit_btn.count() > 0 and submit_btn.first.is_visible():
                    submit_btn.first.click()
                else:
                    page.keyboard.press("Enter")
                page.wait_for_timeout(4000)

            # Check for alternative sign-in options if QR code is behind a selection
            for alt_sel in [
                "a#signInAnotherWay",
                "div[data-value='QrCode']",
                "div[data-value='PhoneAppNotification']",
                "span:has-text('QR')",
                "span:has-text('Microsoft Authenticator')"
            ]:
                try:
                    loc = page.locator(alt_sel)
                    if loc.count() > 0 and loc.first.is_visible():
                        loc.first.click()
                        page.wait_for_timeout(3000)
                        break
                except Exception:
                    pass

            page.wait_for_timeout(2000)
            page.screenshot(path=str(temp_qr_path), full_page=False)

            notifier.send_telegram_photo(
                temp_qr_path,
                caption=(
                    "📸 <b>【SPeCTRUM Microsoft Sign-In QR】</b>\n\n"
                    "1. Open your phone's <b>Microsoft Authenticator</b> app.\n"
                    "2. Scan the QR code or approve the prompt displayed above.\n\n"
                    "⏳ <i>Waiting up to 3 minutes for authorization...</i>"
                ),
                chat_id=chat_id
            )

            # Poll for up to 180 seconds for login approval
            poll_start = time.time()
            success = False
            while time.time() - poll_start < 180:
                time.sleep(3)
                try:
                    c_url = page.url.lower()

                    # Handle Microsoft 'Stay signed in?' (KMSI) prompt
                    kmsi_btn = page.locator("#idSIButton9, input[value='Yes'], button:has-text('Yes')")
                    if kmsi_btn.count() > 0 and "kmsi" in c_url:
                        kmsi_btn.first.click()
                        page.wait_for_timeout(2000)
                        continue

                    has_logout = page.locator("a[href*='login/logout.php']").count() > 0
                    is_body_loggedin = page.locator("body.loggedin").count() > 0

                    if not ("login" in c_url or "microsoftonline" in c_url) and (has_logout or is_body_loggedin):
                        success = True
                        break
                except Exception:
                    pass

            if success:
                time.sleep(2)
                context.storage_state(path=str(config.AUTH_STATE_FILE))
                notifier.send_telegram_message(
                    "🎉 <b>【SPeCTRUM Login Successful】</b>\n\n"
                    "Your session has been securely saved to the bot!\n"
                    "Background monitoring and deadline tracking are running normally.",
                    chat_id=chat_id
                )
            else:
                notifier.send_telegram_message(
                    "⏳ <b>Login Timed Out</b>\n\n"
                    "No approved authentication was detected within 3 minutes.\n"
                    "Send <code>/login</code> anytime to try again.",
                    chat_id=chat_id
                )

            browser.close()
            return success

    except Exception as e:
        logger.error(f"Remote login error: {e}", exc_info=True)
        notifier.send_telegram_message(f"❌ <b>Login Error:</b> {html.escape(str(e))}", chat_id=chat_id)
        return False
    finally:
        try:
            temp_qr_path.unlink(missing_ok=True)
        except Exception:
            pass

if __name__ == "__main__":
    interactive_login()
