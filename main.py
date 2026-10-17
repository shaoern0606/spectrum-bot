import argparse
import logging
import sys
import threading
import time
from datetime import datetime
from typing import Optional
import config
import storage
import notifier
from scraper import SpectrumScraper
from login import interactive_login
from bot_listener import TelegramBotListener

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("SpectrumBot")

def is_recent_announcement(posted_time_str: str, max_days: int = 14) -> bool:
    """
    Checks if an announcement is recent (posted within the last max_days).
    Prevents historical posts from recycled courses (e.g. 2024, 2025) from spamming notifications.
    """
    if not posted_time_str:
        return True
    import re
    clean = re.sub(r'^(Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s*', '', posted_time_str.strip())
    lower = clean.lower()
    if any(k in lower for k in ['just now', 'today', 'yesterday', 'minute', 'hour']):
        return True
    now = datetime.now()
    year_match = re.search(r'\b(20\d\d)\b', clean)
    if year_match:
        post_year = int(year_match.group(1))
        if post_year < now.year:
            return False
    for fmt in [
        '%d %b %Y, %I:%M %p', '%d %B %Y, %I:%M %p',
        '%d %b %Y', '%d %B %Y',
        '%d/%m/%Y', '%Y-%m-%d'
    ]:
        try:
            dt = datetime.strptime(clean, fmt)
            diff_days = (now - dt).total_seconds() / 86400.0
            return diff_days <= max_days
        except ValueError:
            pass
    return True

def perform_check(force_notify_all: bool = False, reply_to_chat_id: Optional[str] = None) -> None:
    """Executes a full scrape and notification check."""
    logger.info("========== Starting SPeCTRUM Check ==========")
    storage.init_db()
    first_run = storage.is_database_empty()

    if first_run and not force_notify_all:
        logger.info("💡 First run detected: establishing initial baseline (won't spam historical files)...")

    try:
        with SpectrumScraper(headless=True) as scraper:
            page = scraper.context.new_page()

            # 1. Verify session validity
            is_auth, is_maintenance = scraper.check_auth_valid(page)
            if is_maintenance:
                logger.warning("🚧 SPeCTRUM is temporarily offline for scheduled UM ICT maintenance. Check will retry next interval.")
                if reply_to_chat_id:
                    notifier.send_telegram_message("🚧 <b>【SPeCTRUM ICT Maintenance】</b>\n\nUM SPeCTRUM is currently offline for scheduled ICT maintenance (expected 6:00 PM - 9:00 PM tonight).\n\nChecks will automatically resume once the portal is back online.", chat_id=reply_to_chat_id)
                return

            if not is_auth:
                logger.error("❌ SPeCTRUM session has expired or is invalid!")
                notifier.notify_auth_expired()
                print("\n⚠️ Session expired. Please run `python main.py --login` to re-authenticate.\n")
                if reply_to_chat_id:
                    notifier.send_telegram_message("⚠️ SPeCTRUM session has expired. Please ask the bot host to run `python main.py --login`.", chat_id=reply_to_chat_id)
                return

            # 2. Get enrolled courses
            courses = scraper.get_enrolled_courses(page)
            if not courses:
                logger.warning("No valid courses found on dashboard. Please check account permissions or page layout.")
                if reply_to_chat_id:
                    notifier.send_telegram_message("⚠️ No enrolled courses detected on SPeCTRUM dashboard.", chat_id=reply_to_chat_id)
                return

            # 2.5 Scrape upcoming calendar deadlines
            try:
                courses_map = {c["id"]: c["full_name"] for c in courses}
                cal_deadlines = scraper.scrape_upcoming_deadlines(page, courses_map=courses_map)
                for d in cal_deadlines:
                    storage.upsert_assignment(d)
            except Exception as err:
                logger.warning(f"Error scraping upcoming deadlines: {err}")

            total_new_res = 0
            total_new_ann = 0
            all_res_count = 0
            all_ann_count = 0

            # 3. Check each course
            for c in courses:
                c_id = c["id"]
                c_name = c["full_name"]
                
                # Check if this course is new to the database
                is_new_course = storage.is_course_new(c_id)
                storage.upsert_course(c_id, c_name, c["url"])

                resources, announcements = scraper.scrape_course_content(page, c)
                all_res_count += len(resources)
                all_ann_count += len(announcements)

                if (first_run or is_new_course) and not force_notify_all:
                    # Save baseline silently for new courses or initial run - DO NOT SPAM
                    logger.info(f"Baseline saved silently for '{c_name}': {len(resources)} items, {len(announcements)} posts.")
                    storage.save_resources(resources)
                    storage.save_announcements(announcements)
                    continue

                # Diff check resources
                new_resources = storage.filter_new_resources(c_id, resources)
                course_instructions_init = storage.is_course_instructions_initialized(c_id)

                for res in new_resources:
                    # If this course had no instructions recorded before (first run with this feature),
                    # save existing section instructions silently so old weeks don't spam!
                    if res.get("activity_type") == "instruction" and not course_instructions_init:
                        logger.info(f"Silently baselining existing section instruction: [{c_name}] -> {res['title']}")
                        storage.save_resources([res])
                        continue

                    logger.info(f"✨ New resource found: [{c_name}] -> {res['title']}")
                    ok = notifier.notify_new_resource(c_name, res)
                    if ok:
                        storage.save_resources([res])
                        total_new_res += 1
                    else:
                        logger.error(f"Failed to deliver notification for resource '{res['title']}'. Will retry on next check.")

                # Diff check announcements
                new_announcements = storage.filter_new_announcements(c_id, announcements)
                for ann in new_announcements:
                    posted_str = ann.get("posted_time", "")
                    if not is_recent_announcement(posted_str, max_days=14):
                        logger.info(f"Silently saving historical announcement ({posted_str}): [{c_name}] -> {ann['title']}")
                        storage.save_announcements([ann])
                        continue

                    logger.info(f"📢 New announcement found: [{c_name}] -> {ann['title']}")
                    ok = notifier.notify_new_announcement(c_name, ann)
                    if ok:
                        storage.save_announcements([ann])
                        total_new_ann += 1
                    else:
                        logger.error(f"Failed to deliver notification for announcement '{ann['title']}'. Will retry on next check.")

                # Check and sync course assignments & quizzes
                task_activities = [r for r in resources if r.get("activity_type") in ("assign", "quiz")]
                if task_activities:
                    try:
                        scraper.scrape_course_assignments(page, c, task_activities)
                    except Exception as err:
                        logger.warning(f"Error checking course tasks for '{c_name}': {err}")

            # 4. Check for urgent approaching deadlines
            try:
                impending = storage.get_impending_deadline_warnings()
                for item in impending:
                    threshold = item.get("threshold", "48h")
                    hours_left = item.get("hours_left", 24)
                    logger.info(f"⏰ Sending deadline warning ({threshold}): [{item['course_name']}] -> {item['title']}")
                    ok = notifier.notify_deadline_urgent(item, hours_left)
                    if ok:
                        storage.mark_assignment_warned(item["id"], threshold)
            except Exception as err:
                logger.warning(f"Error checking deadline warnings: {err}")

            if first_run and not force_notify_all:
                logger.info(f"✅ Baseline sync complete: {len(courses)} courses, {all_res_count} resources, {all_ann_count} announcements.")
                notifier.notify_startup_status(len(courses), all_res_count, all_ann_count)
            else:
                logger.info(f"Check complete. Found: {total_new_res} new resources, {total_new_ann} new announcements.")
                if reply_to_chat_id:
                    if total_new_res == 0 and total_new_ann == 0:
                        notifier.send_telegram_message("✅ <b>【SPeCTRUM Check Complete】</b>\n\nAll courses are up to date. No new materials or announcements found.", chat_id=reply_to_chat_id)
                    else:
                        notifier.send_telegram_message(f"✅ <b>【SPeCTRUM Check Complete】</b>\n\nFound <b>{total_new_res}</b> new resource(s) and <b>{total_new_ann}</b> new announcement(s). Delivered above.", chat_id=reply_to_chat_id)

    except FileNotFoundError as e:
        logger.error(e)
        if reply_to_chat_id:
            notifier.send_telegram_message(f"❌ Error: {e}", chat_id=reply_to_chat_id)
    except Exception as e:
        logger.exception(f"Unhandled exception during check: {e}")
        if reply_to_chat_id:
            notifier.send_telegram_message(f"❌ Check exception: {e}", chat_id=reply_to_chat_id)

def test_telegram():
    """Sends a test ping to Telegram with menu buttons."""
    logger.info("Sending test ping to Telegram...")
    valid, msg = config.validate_config(require_telegram=True)
    if not valid:
        print(f"❌ Configuration error: {msg}")
        return
    success = notifier.send_main_menu(
        "👋 <b>【SpectrumBot Connection Successful】</b>\n\n"
        "Congratulations! Your Telegram Bot is successfully configured and the control panel is active!\n"
        "You can now tap the buttons below to interact with the bot."
    )
    if success:
        print("✅ Telegram message and menu buttons sent successfully! Check your Telegram app.")
    else:
        print("❌ Failed to send Telegram message. Please check BOT_TOKEN and CHAT_ID in .env.")

def auto_detect_chat_id():
    """Listens to the user's bot to auto-detect their chat ID and saves it to .env."""
    if not config.TELEGRAM_BOT_TOKEN or config.TELEGRAM_BOT_TOKEN == "your_bot_token_here":
        print("❌ Please set TELEGRAM_BOT_TOKEN in .env first.")
        return

    print("\n" + "="*60)
    print("🤖 Telegram Chat ID Auto-Detector")
    print("="*60)
    print("1. Open Telegram and search for your newly created bot.")
    print("2. Send ANY message to your bot (e.g. 'hello' or '/start').")
    print("⏳ Listening for incoming messages (waiting up to 60s)...")
    print("="*60 + "\n")

    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getUpdates"
    start_time = time.time()
    
    try:
        r = requests.get(url, timeout=10).json()
        existing = r.get("result", [])
        offset = (existing[-1]["update_id"] + 1) if existing else 0
    except Exception:
        offset = 0

    while time.time() - start_time < 60:
        try:
            resp = requests.get(url, params={"offset": offset, "timeout": 5}, timeout=10).json()
            updates = resp.get("result", [])
            for u in updates:
                msg = u.get("message") or u.get("callback_query", {}).get("message")
                if msg:
                    from_user = u.get("message", {}).get("from") or u.get("callback_query", {}).get("from", {})
                    chat = msg.get("chat", {})
                    cid = str(chat.get("id", ""))
                    name = from_user.get("first_name", "User")
                    username = f" (@{from_user.get('username')})" if from_user.get('username') else ""
                    
                    print(f"\n🎉 Message received from {name}{username}!")
                    print(f"👉 Your TELEGRAM_CHAT_ID is: {cid}")
                    
                    env_path = config.BASE_DIR / ".env"
                    if env_path.exists():
                        content = env_path.read_text(encoding="utf-8")
                        import re
                        if "TELEGRAM_CHAT_ID=" in content:
                            new_content = re.sub(r"TELEGRAM_CHAT_ID=.*", f"TELEGRAM_CHAT_ID={cid}", content)
                        else:
                            new_content = content + f"\nTELEGRAM_CHAT_ID={cid}\n"
                        env_path.write_text(new_content, encoding="utf-8")
                        print(f"✅ Automatically updated TELEGRAM_CHAT_ID in {env_path.name}!")
                    print("\nYou can now run `python main.py --test-tg` to verify connection.\n")
                    return
        except Exception:
            pass
        time.sleep(1)
    
    print("\n⚠️ No message detected within 60s. Make sure you sent a message to your bot on Telegram!")

def run_watcher():
    """Runs periodic monitoring daemon with interactive Telegram bot listener."""
    interval_sec = config.CHECK_INTERVAL_MINUTES * 60
    logger.info(f"🚀 SpectrumBot daemon started. Automatically checking every {config.CHECK_INTERVAL_MINUTES} minutes.")

    # 1. Start background thread for startup check & periodic timer
    def _periodic_loop():
        perform_check()
        last_check_time = datetime.now()
        logger.info(f"⏳ Sleeping... Next automatic check in {config.CHECK_INTERVAL_MINUTES} minutes.")
        while True:
            # Check in short 10s increments so laptop wake-from-sleep is detected immediately
            time.sleep(10)
            elapsed = (datetime.now() - last_check_time).total_seconds()
            if elapsed >= interval_sec:
                try:
                    logger.info("⏱️ Periodic interval reached (or woke from sleep). Starting automatic check...")
                    perform_check()
                except Exception as e:
                    logger.error(f"Periodic check error: {e}")
                last_check_time = datetime.now()
                logger.info(f"⏳ Sleeping... Next automatic check in {config.CHECK_INTERVAL_MINUTES} minutes.")

    timer_thread = threading.Thread(target=_periodic_loop, daemon=True)
    timer_thread.start()

    # 2. Start Telegram bot listener IMMEDIATELY on main thread so buttons respond instantly
    listener = TelegramBotListener(on_check_requested=lambda cid: perform_check(reply_to_chat_id=cid))
    try:
        listener.start_polling()
    except KeyboardInterrupt:
        logger.info("Stopped by user. Daemon shutting down.")
        listener.stop()

def main():
    parser = argparse.ArgumentParser(description="SpectrumBot: UM SPeCTRUM Course Materials & Announcements Telegram Bot")
    parser.add_argument("--login", action="store_true", help="Launch interactive browser to complete SSO / 2FA login and save session")
    parser.add_argument("--check", action="store_true", help="Run an immediate check for new course materials and announcements")
    parser.add_argument("--watch", action="store_true", help="Start background monitoring daemon with interactive Telegram button listener")
    parser.add_argument("--test-tg", action="store_true", help="Test Telegram Bot connection and activate the bottom keyboard menu")
    parser.add_argument("--get-chat-id", action="store_true", help="Listen to your bot and automatically detect and save your Telegram Chat ID")
    args = parser.parse_args()

    if args.login:
        interactive_login()
    elif args.get_chat_id:
        auto_detect_chat_id()
    elif args.test_tg:
        test_telegram()
    elif args.check:
        perform_check(reply_to_chat_id=config.TELEGRAM_CHAT_ID)
    elif args.watch:
        run_watcher()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
