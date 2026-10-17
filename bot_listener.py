import html
import logging
import threading
import time
from typing import Callable, Optional
import requests
import config
import notifier
import storage

logger = logging.getLogger(__name__)

class TelegramBotListener:
    def __init__(self, on_check_requested: Optional[Callable[[], None]] = None):
        self.on_check_requested = on_check_requested
        self.running = False
        self.offset = 0
        self._check_lock = threading.Lock()

    def start_polling(self):
        """Starts polling Telegram for user messages and button clicks."""
        valid, msg = config.validate_config(require_telegram=True)
        if not valid:
            logger.error(f"Cannot start Telegram listener: {msg}")
            return

        logger.info("🤖 Telegram interactive bot listener service started...")
        self.running = True

        # Send initial keyboard to user
        try:
            notifier.send_main_menu()
        except Exception as e:
            logger.warning(f"Failed to send initial menu: {e}")

        while self.running:
            try:
                url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getUpdates"
                params = {
                    "offset": self.offset,
                    "timeout": 20,
                    "allowed_updates": ["message", "callback_query"]
                }
                resp = requests.get(url, params=params, timeout=30)
                if resp.status_code != 200:
                    time.sleep(3)
                    continue

                data = resp.json()
                if not data.get("ok"):
                    time.sleep(3)
                    continue

                updates = data.get("result", [])
                for update in updates:
                    self.offset = update["update_id"] + 1
                    self._handle_update(update)

            except requests.exceptions.Timeout:
                continue
            except requests.exceptions.RequestException as e:
                logger.warning(f"Telegram network connection dropped: {e}. Retrying in 5 seconds...")
                time.sleep(5)
            except Exception as e:
                logger.error(f"Error handling Telegram message: {e}")
                time.sleep(2)

    def stop(self):
        self.running = False

    def _handle_update(self, update: dict):
        """Parses update and handles commands, text buttons, and callback queries."""
        # 1. Handle inline button clicks (Callback Queries)
        cb_query = update.get("callback_query")
        if cb_query:
            self._handle_callback_query(cb_query)
            return

        # 2. Handle regular text messages & keyboard buttons
        msg = update.get("message")
        if not msg:
            return

        chat = msg.get("chat", {})
        chat_id = str(chat.get("id", ""))
        from_user = msg.get("from", {})
        first_name = from_user.get("first_name", "")
        username = from_user.get("username", "")

        text = (msg.get("text") or "").strip()
        logger.info(f"Received message from {first_name or 'User'} ({chat_id}): {text}")

        is_admin = bool(config.TELEGRAM_CHAT_ID and chat_id == str(config.TELEGRAM_CHAT_ID).strip())
        is_approved = storage.is_user_approved(chat_id)

        # Gatekeeper: Block unauthorized strangers
        if not is_approved:
            logger.warning(f"Unauthorized access blocked: {first_name} (@{username}, ID: {chat_id}): '{text}'")
            storage.add_subscriber(chat_id, first_name, username, is_approved=0)
            
            notifier.send_telegram_message(
                "🔒 <b>【Access Restricted / 私有机器人】</b>\n\n"
                f"Hello {html.escape(first_name or 'there')}, SpectrumBot is a private service.\n\n"
                "Your access request has been sent to the administrator for review.",
                chat_id=chat_id
            )
            
            # Send approval request with buttons to Admin
            if config.TELEGRAM_CHAT_ID and not is_admin:
                admin_msg = (
                    "🔔 <b>【New Access Request / 新用户申请】</b>\n\n"
                    f"👤 <b>Name:</b> {html.escape(first_name or 'Unknown')}\n"
                    f"🏷️ <b>Username:</b> @{html.escape(username or 'none')}\n"
                    f"🆔 <b>Chat ID:</b> <code>{chat_id}</code>\n\n"
                    "Would you like to grant this user access to your SpectrumBot?"
                )
                admin_keyboard = {
                    "inline_keyboard": [
                        [
                            {"text": "✅ Approve / 批准", "callback_data": f"auth_app:{chat_id}"},
                            {"text": "❌ Deny / 拒绝", "callback_data": f"auth_deny:{chat_id}"}
                        ]
                    ]
                }
                notifier.send_telegram_message(admin_msg, reply_markup=admin_keyboard, chat_id=str(config.TELEGRAM_CHAT_ID))
            return

        # Auto-subscribe approved user on /start
        if text in ["/start", "menu"]:
            storage.add_subscriber(chat_id, first_name, username, is_approved=1)
            logger.info(f"Registered/Refreshed subscriber: {first_name} ({chat_id})")
            notifier.send_main_menu(
                f"👋 <b>Welcome to SpectrumBot, {html.escape(first_name or 'Friend')}!</b>\n\n"
                "You are subscribed to SPeCTRUM lecture notes and announcement updates!\n\n"
                "Tap any button below to get started:",
                chat_id=chat_id
            )
            return

        elif text in ["🔍 Check Now", "🔍 立即检查", "/check"]:
            if self._check_lock.locked():
                notifier.send_telegram_message("⏳ Check already in progress. Please wait a moment...", chat_id=chat_id)
                return

            def _run_check_async(target_cid: str):
                with self._check_lock:
                    notifier.send_telegram_message("🔎 <b>Connecting to SPeCTRUM to check updates...</b>\nPlease wait 10~30 seconds. Results will be posted here.", chat_id=target_cid)
                    if self.on_check_requested:
                        try:
                            self.on_check_requested(target_cid)
                        except Exception as err:
                            notifier.send_telegram_message(f"❌ Check error: {err}", chat_id=target_cid)

            thread = threading.Thread(target=_run_check_async, args=(chat_id,), daemon=True)
            thread.start()

        elif text in ["📚 My Courses", "📚 我的课程", "/courses", "/files"]:
            courses = storage.get_courses_summary()
            notifier.send_courses_list(courses, chat_id=chat_id)

        elif text in ["📝 Deadlines", "📝 Assignments", "📝 待办与作业", "/deadlines", "/assignments", "/tasks"]:
            categorized = storage.get_categorized_assignments()
            notifier.send_assignments_dashboard(categorized, chat_id=chat_id)

        elif text.startswith("/search") or text.startswith("/find"):
            parts = text.split(maxsplit=1)
            query = parts[1].strip() if len(parts) > 1 else ""
            if not query:
                notifier.send_telegram_message(
                    "💡 <b>Please enter search keywords</b>\n\n"
                    "Examples:\n"
                    "• <code>/search lecture 1</code>\n"
                    "• <code>/search assignment</code>\n"
                    "• <code>/search tutorial</code>",
                    chat_id=chat_id
                )
            else:
                results = storage.search_resources(query, limit=8)
                notifier.send_search_results(query, results, chat_id=chat_id)

        elif text in ["⚙️ Status", "⚙️ 监控状态", "/status"]:
            stats = storage.get_system_stats()
            is_logged_in = config.AUTH_STATE_FILE.exists()
            notifier.send_system_status(stats, is_logged_in=is_logged_in, chat_id=chat_id)

        elif text.startswith("/login"):
            if chat_id != str(config.TELEGRAM_CHAT_ID):
                notifier.send_telegram_message("⚠️ Only the bot host can update SPeCTRUM login credentials.", chat_id=chat_id)
                return

            email_param = None
            parts = text.split()
            if len(parts) > 1 and "@" in parts[1]:
                email_param = parts[1].strip()

            def _async_login():
                from login import remote_telegram_login
                remote_telegram_login(chat_id=chat_id, email=email_param)

            threading.Thread(target=_async_login, daemon=True).start()

        elif text in ["/users", "/whitelist"] and is_admin:
            subs = storage.list_subscribers_status()
            if not subs:
                notifier.send_telegram_message("📋 No registered subscribers found.", chat_id=chat_id)
            else:
                lines = ["👥 <b>【SpectrumBot Authorized Users】</b>\n"]
                for s in subs:
                    cid = s['chat_id']
                    name = html.escape(s.get('first_name') or 'User')
                    uname = f" (@{html.escape(s['username'])})" if s.get('username') else ""
                    if cid == str(config.TELEGRAM_CHAT_ID).strip():
                        tag = "👑 <i>Admin</i>"
                    elif s.get('is_approved'):
                        tag = "✅ <i>Approved</i>"
                    else:
                        tag = "⏳ <i>Pending</i>"
                    lines.append(f"• <b>{name}</b>{uname}\n  ID: <code>{cid}</code> | {tag}")
                lines.append("\n💡 <i>Commands:</i>\n<code>/allow &lt;chat_id&gt;</code> to approve\n<code>/revoke &lt;chat_id&gt;</code> to block")
                notifier.send_telegram_message("\n".join(lines), chat_id=chat_id)

        elif text.startswith("/allow") and is_admin:
            parts = text.split()
            if len(parts) > 1 and parts[1].strip().isdigit():
                target_cid = parts[1].strip()
                storage.approve_subscriber(target_cid)
                notifier.send_telegram_message(f"✅ User <code>{target_cid}</code> has been approved!", chat_id=chat_id)
                notifier.send_main_menu(
                    "🎉 <b>Your access has been approved by the administrator!</b>\n\n"
                    "You now have access to SPeCTRUM lecture notes and updates.\nTap any button below to get started:",
                    chat_id=target_cid
                )
            else:
                notifier.send_telegram_message("💡 Usage: <code>/allow &lt;chat_id&gt;</code>", chat_id=chat_id)

        elif text.startswith("/revoke") and is_admin:
            parts = text.split()
            if len(parts) > 1 and parts[1].strip().isdigit():
                target_cid = parts[1].strip()
                if target_cid == str(config.TELEGRAM_CHAT_ID).strip():
                    notifier.send_telegram_message("❌ You cannot revoke the admin account.", chat_id=chat_id)
                else:
                    storage.block_subscriber(target_cid)
                    notifier.send_telegram_message(f"❌ User <code>{target_cid}</code> has been revoked / blocked.", chat_id=chat_id)
            else:
                notifier.send_telegram_message("💡 Usage: <code>/revoke &lt;chat_id&gt;</code>", chat_id=chat_id)

        elif text in ["❓ Help", "❓ 使用帮助", "/help"]:
            extra_admin_help = (
                "\n\n👑 <b>Admin Commands:</b>\n"
                "• <code>/users</code> - List all authorized and pending users\n"
                "• <code>/allow &lt;id&gt;</code> - Whitelist a user\n"
                "• <code>/revoke &lt;id&gt;</code> - Revoke a user's access"
            ) if is_admin else ""
            notifier.send_help_message(chat_id=chat_id)
            if extra_admin_help:
                notifier.send_telegram_message(extra_admin_help, chat_id=chat_id)

        else:
            # Check if user typed keywords directly (e.g. "lecture 1" or "sql")
            results = storage.search_resources(text, limit=5)
            if results and len(text) >= 3 and not text.startswith("/"):
                notifier.send_search_results(text, results, chat_id=chat_id)
            else:
                notifier.send_main_menu(
                    f"Received command: <code>{html.escape(text)}</code>\n\nPlease tap any button below to choose an action:",
                    chat_id=chat_id
                )

    def _handle_callback_query(self, cb_query: dict):
        """Handles inline button clicks like downloading files."""
        query_id = cb_query.get("id")
        data = cb_query.get("data", "")
        from_user = cb_query.get("from", {})
        chat_id = str(from_user.get("id", ""))
        first_name = from_user.get("first_name", "Friend")
        is_admin = bool(config.TELEGRAM_CHAT_ID and chat_id == str(config.TELEGRAM_CHAT_ID).strip())

        logger.info(f"Received callback action '{data}' from {first_name} ({chat_id})")

        # Always acknowledge callback query
        def _ack(toast_text=None):
            try:
                payload = {"callback_query_id": query_id}
                if toast_text:
                    payload["text"] = toast_text
                requests.post(
                    f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/answerCallbackQuery",
                    json=payload,
                    timeout=10
                )
            except Exception:
                pass

        # Handle Admin User Approval Buttons
        if data.startswith("auth_app:"):
            if not is_admin:
                _ack("❌ Only administrator can approve users.")
                return
            target_cid = data.split(":", 1)[1]
            storage.approve_subscriber(target_cid)
            _ack("✅ Approved!")
            notifier.send_telegram_message(
                f"✅ <b>Approved User!</b>\nChat ID <code>{target_cid}</code> now has access.",
                chat_id=chat_id
            )
            notifier.send_main_menu(
                "🎉 <b>Your access has been approved by the administrator!</b>\n\n"
                "You now have access to SPeCTRUM lecture notes and updates.\nTap any button below to get started:",
                chat_id=target_cid
            )
            return

        elif data.startswith("auth_deny:"):
            if not is_admin:
                _ack("❌ Only administrator can deny users.")
                return
            target_cid = data.split(":", 1)[1]
            storage.block_subscriber(target_cid)
            _ack("❌ Denied.")
            notifier.send_telegram_message(
                f"❌ <b>Denied User</b>\nChat ID <code>{target_cid}</code> was blocked.",
                chat_id=chat_id
            )
            notifier.send_telegram_message(
                "⛔ <b>Access Denied</b>\nYour request to use SpectrumBot was declined by the administrator.",
                chat_id=target_cid
            )
            return

        # Check authorization for other actions
        if not storage.is_user_approved(chat_id):
            _ack("🔒 Access Restricted. Private Bot.")
            return

        if data.startswith("dl:"):
            res_id = data[3:]
            _ack("⏳ Downloading file from SPeCTRUM...")

            def _async_send():
                notifier.send_resource_file_to_chat(res_id, chat_id=chat_id)

            threading.Thread(target=_async_send, daemon=True).start()

        elif data.startswith("browse:"):
            _ack()
            course_id = data.split(":", 1)[1]
            course = storage.get_course_by_id(course_id)
            if course:
                sections = storage.get_course_sections(course_id)
                notifier.send_course_browser(course, sections, chat_id=chat_id)
            else:
                notifier.send_telegram_message("❌ Course not found in database.", chat_id=chat_id)

        elif data.startswith("sec:"):
            _ack()
            parts = data.split(":")
            if len(parts) >= 3:
                course_id = parts[1]
                try:
                    sec_idx = int(parts[2])
                except ValueError:
                    sec_idx = 0
                course = storage.get_course_by_id(course_id)
                sections = storage.get_course_sections(course_id)
                if course and 0 <= sec_idx < len(sections):
                    sec_name = sections[sec_idx]
                    resources = storage.get_resources_by_course_and_section(course_id, sec_name)
                    notifier.send_section_resources(course, sec_name, resources, chat_id=chat_id)
                else:
                    notifier.send_telegram_message("❌ Section not found.", chat_id=chat_id)

        elif data == "back_courses":
            _ack()
            courses = storage.get_courses_summary()
            notifier.send_courses_list(courses, chat_id=chat_id)

        elif data == "ref_deadlines":
            _ack("🔄 Refreshing deadlines from SPeCTRUM...")

            def _async_refresh():
                from scraper import SpectrumScraper
                try:
                    with SpectrumScraper(headless=True) as sc:
                        p = sc.context.new_page()
                        is_auth, _ = sc.check_auth_valid(p)
                        if is_auth:
                            deadlines = sc.scrape_upcoming_deadlines(p)
                            for d in deadlines:
                                storage.upsert_assignment(d)
                    cat = storage.get_categorized_assignments()
                    notifier.send_assignments_dashboard(cat, chat_id=chat_id)
                except Exception as err:
                    logger.error(f"Error refreshing deadlines: {err}")
                    notifier.send_telegram_message(f"⚠️ Failed to refresh deadlines: {err}", chat_id=chat_id)

            threading.Thread(target=_async_refresh, daemon=True).start()
        else:
            _ack()
