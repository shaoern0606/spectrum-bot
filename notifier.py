import html
import logging
import time
from typing import Any, Dict, List, Optional
import requests
import config

logger = logging.getLogger(__name__)

# Persistent keyboard menu shown at the bottom of the Telegram chat
MAIN_KEYBOARD = {
    "keyboard": [
        [{"text": "🔍 Check Now"}, {"text": "📚 My Courses"}],
        [{"text": "⚙️ Status"}, {"text": "❓ Help"}]
    ],
    "resize_keyboard": True,
    "is_persistent": True
}

def send_telegram_message(
    text: str, 
    parse_mode: str = "HTML", 
    disable_preview: bool = False,
    reply_markup: Optional[Dict[str, Any]] = None,
    chat_id: Optional[str] = None
) -> bool:
    """Sends a message via the Telegram Bot API."""
    valid, err_msg = config.validate_config(require_telegram=True)
    if not valid:
        logger.warning(f"Cannot send Telegram message: {err_msg}")
        return False

    target_chat_id = chat_id or config.TELEGRAM_CHAT_ID
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": target_chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": disable_preview,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    for attempt in range(1, 4):
        try:
            response = requests.post(url, json=payload, timeout=20)
            res_json = response.json()
            if not res_json.get("ok"):
                logger.error(f"Telegram API returned error: {res_json.get('description')}")
                return False
            return True
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            logger.warning(f"Telegram network glitch sending message (attempt {attempt}/3): {e}")
            if attempt < 3:
                time.sleep(1.5 * attempt)
        except Exception as e:
            logger.error(f"Exception sending Telegram message: {e}")
            return False
    return False

def send_telegram_document(
    file_path: Path,
    filename: str,
    caption: str,
    chat_id: Optional[str] = None
) -> bool:
    """Uploads and sends a document/file via Telegram Bot API."""
    target_chat_id = chat_id or config.TELEGRAM_CHAT_ID
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendDocument"
    for attempt in range(1, 4):
        try:
            with open(file_path, "rb") as f:
                files = {"document": (filename, f)}
                data = {
                    "chat_id": target_chat_id,
                    "caption": caption,
                    "parse_mode": "HTML"
                }
                resp = requests.post(url, data=data, files=files, timeout=90)
                res_json = resp.json()
                if not res_json.get("ok"):
                    logger.error(f"Failed to send document: {res_json.get('description')}")
                    return False
                return True
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            logger.warning(f"Telegram network glitch sending document (attempt {attempt}/3): {e}")
            if attempt < 3:
                time.sleep(2.0 * attempt)
        except Exception as e:
            logger.error(f"Exception sending document: {e}")
            return False
    return False

def send_telegram_photo(
    photo_path: Path,
    caption: str = "",
    chat_id: Optional[str] = None
) -> bool:
    """Uploads and sends a photo/screenshot via Telegram Bot API."""
    if not config.TELEGRAM_BOT_TOKEN:
        return False
    target_chat_id = chat_id or config.TELEGRAM_CHAT_ID
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendPhoto"
    try:
        with open(photo_path, "rb") as f:
            files = {"photo": (photo_path.name, f)}
            data = {
                "chat_id": target_chat_id,
                "caption": caption,
                "parse_mode": "HTML"
            }
            resp = requests.post(url, data=data, files=files, timeout=60)
            res_json = resp.json()
            if not res_json.get("ok"):
                logger.error(f"Failed to send photo: {res_json.get('description')}")
                return False
            return True
    except Exception as e:
        logger.error(f"Exception sending photo: {e}")
        return False

def send_resource_file_to_chat(resource_id: str, chat_id: Optional[str] = None) -> bool:
    """Downloads a resource and sends the actual file into Telegram chat."""
    import storage
    import downloader

    target_chat_id = chat_id or config.TELEGRAM_CHAT_ID
    res = storage.get_resource_by_id(resource_id)
    if not res:
        send_telegram_message("❌ Resource not found in database.", chat_id=target_chat_id)
        return False

    temp_path, filename, err = downloader.download_moodle_resource(res["url"], res["title"])
    if err or not temp_path or not temp_path.exists():
        if "TOO_LARGE" in str(err) or "too large" in str(err).lower():
            size_info = str(err).replace("TOO_LARGE:", "").strip()
            msg = (
                "📦 <b>【File Exceeds Telegram 50MB Limit】</b>\n\n"
                f"📄 <b>File:</b> {html.escape(res.get('title', 'Document'))}\n"
                f"📊 <b>Size:</b> {size_info}\n\n"
                "Telegram Bot API does not permit bots to upload files larger than 50MB.\n"
                "Please tap the button below to download the file directly from SPeCTRUM:"
            )
            inline_keyboard = {
                "inline_keyboard": [[{"text": "🔗 Open & Download on SPeCTRUM", "url": res["url"]}]]
            }
            send_telegram_message(msg, reply_markup=inline_keyboard, chat_id=target_chat_id)
            return False

        send_telegram_message(f"⚠️ Could not download file: {err or 'Unknown error'}", chat_id=target_chat_id)
        return False

    caption = (
        f"📄 <b>{html.escape(filename)}</b>\n"
        f"📌 <i>{html.escape(res.get('title', ''))}</i>"
    )
    success = send_telegram_document(temp_path, filename, caption, chat_id=target_chat_id)

    try:
        temp_path.unlink(missing_ok=True)
    except Exception:
        pass

    return success

def notify_new_resource(course_name: str, item: Dict[str, Any], chat_id: Optional[str] = None) -> bool:
    """Notify user about a newly uploaded file/slide/resource with an inline button."""
    import storage
    title = html.escape(item.get("title", "Untitled Resource"))
    section = html.escape(item.get("section_name", "Course Content"))
    c_name = html.escape(course_name)
    act_type = item.get("activity_type", "resource").upper()
    url = item.get("url", config.SPECTRUM_BASE_URL)

    icon = "📄"
    header = f"【SPeCTRUM: New {act_type} Uploaded】"
    if "INSTRUCTION" in act_type:
        icon = "📌"
        header = "【SPeCTRUM: Section Notes & Guidelines】"
    elif "PDF" in act_type or "SLIDE" in act_type or "PPT" in act_type:
        icon = "📑"
    elif "ASSIGN" in act_type:
        icon = "📝"
    elif "QUIZ" in act_type:
        icon = "⏱️"
    elif "FOLDER" in act_type:
        icon = "📁"
    elif "URL" in act_type:
        icon = "🔗"

    snippet = html.escape(item.get("content_snippet", "").strip())
    content_part = f"\n\n💬 <b>Guidelines:</b>\n<i>{snippet}</i>" if snippet else ""

    message = (
        f"{icon} <b>{header}</b>\n\n"
        f"📖 <b>Course:</b> {c_name}\n"
        f"📂 <b>Section:</b> {section}\n"
        f"📌 <b>Topic:</b> {title}"
        f"{content_part}"
    )

    if "INSTRUCTION" in act_type:
        buttons = [{"text": "👉 Open Section on SPeCTRUM", "url": url}]
    else:
        buttons = [{"text": "🔗 Open on SPeCTRUM", "url": url}]
        # Add 'Send File to Chat' button for downloadable materials
        if any(k in act_type for k in ["RESOURCE", "FOLDER", "FILE", "PDF", "SLIDE", "PPT"]):
            buttons.append({"text": "📥 Send File Here", "callback_data": f"dl:{item['id']}"})

    inline_keyboard = {
        "inline_keyboard": [buttons]
    }
    
    target_ids = [chat_id] if chat_id else storage.get_all_subscribers()
    success = True
    for cid in target_ids:
        ok = send_telegram_message(message, disable_preview=True, reply_markup=inline_keyboard, chat_id=cid)
        success = success and ok
    return success

def notify_new_announcement(course_name: str, item: Dict[str, Any], chat_id: Optional[str] = None) -> bool:
    """Notify user about a new course announcement / forum post with an inline button."""
    import storage
    title = html.escape(item.get("title", "Untitled Announcement"))
    c_name = html.escape(course_name)
    raw_author = item.get("author", "Instructor")
    raw_posted = item.get("posted_time", "").strip()
    if raw_posted and raw_posted in raw_author:
        raw_author = raw_author.replace(raw_posted, "")
    raw_author = re.sub(r"[\s\.\·\-\,]+$", "", raw_author).strip() or "Instructor"

    author = html.escape(raw_author)
    posted_time = html.escape(raw_posted) if raw_posted else "Just now"
    snippet = html.escape(item.get("content_snippet", "").strip())
    url = item.get("url", config.SPECTRUM_BASE_URL)

    if len(snippet) > 300:
        snippet = snippet[:300] + "..."

    content_part = f"\n💬 <b>Snippet:</b>\n<i>{snippet}</i>\n" if snippet else ""

    author_time_line = f"👤 <b>Author:</b> {author}"
    if raw_posted:
        author_time_line += f" | 🕒 {posted_time}"

    message = (
        f"📢 <b>【SPeCTRUM: New Announcement】</b>\n\n"
        f"📖 <b>Course:</b> {c_name}\n"
        f"📌 <b>Topic:</b> <b>{title}</b>\n"
        f"{author_time_line}\n"
        f"{content_part}"
    )

    inline_keyboard = {
        "inline_keyboard": [
            [{"text": "👉 View Announcement Details", "url": url}]
        ]
    }
    target_ids = [chat_id] if chat_id else storage.get_all_subscribers()
    success = True
    for cid in target_ids:
        ok = send_telegram_message(message, disable_preview=True, reply_markup=inline_keyboard, chat_id=cid)
        success = success and ok
    return success

def notify_auth_expired() -> bool:
    """Notify host user that SPeCTRUM session has expired."""
    message = (
        "⚠️ <b>【SPeCTRUM Session Expired】</b>\n\n"
        "Your SPeCTRUM session has expired. Automatic silent renewal was attempted but Microsoft requires re-authentication.\n\n"
        "📱 <b>You do NOT need to open your computer!</b>\n"
        "Simply send <code>/login</code> here on Telegram to receive your login QR code directly on your phone."
    )
    return send_telegram_message(message)

def notify_startup_status(course_count: int, resource_count: int, announcement_count: int) -> bool:
    """Send initial synchronization summary with bottom keyboard."""
    message = (
        "🤖 <b>【SpectrumBot Ready & Initial Baseline Synced】</b>\n\n"
        f"✅ Monitored Courses: <b>{course_count}</b>\n"
        f"📚 Tracked Resources: <b>{resource_count}</b> items\n"
        f"📢 Tracked Announcements: <b>{announcement_count}</b> posts\n\n"
        f"⏱️ Automatically checking every <b>{config.CHECK_INTERVAL_MINUTES}</b> minutes. New materials will be pushed here immediately!\n\n"
        "💡 <i>You can use the menu buttons below anytime to check manually or view courses.</i>"
    )
    return send_telegram_message(message, reply_markup=MAIN_KEYBOARD)

def send_main_menu(text: Optional[str] = None, chat_id: Optional[str] = None) -> bool:
    """Sends welcome message and sets up the interactive keyboard."""
    msg = text or (
        "👋 <b>Welcome to SpectrumBot Control Panel</b>\n\n"
        "Tap any button below to get started:\n"
        "• <b>🔍 Check Now</b>: Check SPeCTRUM for updates immediately\n"
        "• <b>📚 My Courses</b>: View list of monitored courses\n"
        "• <b>⚙️ Status</b>: Check system and session status\n"
        "• <b>❓ Help</b>: View instructions and commands"
    )
    return send_telegram_message(msg, reply_markup=MAIN_KEYBOARD, chat_id=chat_id)

def send_courses_list(courses: List[Dict[str, Any]], chat_id: Optional[str] = None) -> bool:
    """Sends the formatted list of monitored courses with interactive Browse buttons."""
    if not courses:
        return send_telegram_message("📭 No courses tracked yet. Run <code>python main.py --check</code> to perform initial sync.", chat_id=chat_id)

    lines = ["📚 <b>【Monitored Courses】</b>\n"]
    buttons = []
    for i, c in enumerate(courses, 1):
        name = html.escape(c["full_name"])
        r_cnt = c.get("resource_count", 0)
        a_cnt = c.get("announcement_count", 0)
        lines.append(f"{i}. <b>{name}</b>\n   ↳ 📑 Resources: {r_cnt} | 📢 Announcements: {a_cnt}")
        
        # Add a short label for the browse button (e.g. course code or shortened name)
        code_part = c["full_name"].split()[0] if c["full_name"] else f"Course {i}"
        buttons.append([{"text": f"📂 Browse {code_part}", "callback_data": f"browse:{c['id']}"}])

    lines.append(f"\nTotal: <b>{len(courses)}</b> courses monitored.\n<i>Tap any button below to browse course materials:</i>")
    inline_keyboard = {"inline_keyboard": buttons}
    return send_telegram_message("\n".join(lines), reply_markup=inline_keyboard, chat_id=chat_id)

def send_course_browser(course: Dict[str, Any], sections: List[str], chat_id: Optional[str] = None) -> bool:
    """Displays sections/chapters of a course with interactive buttons."""
    c_name = html.escape(course["full_name"])
    if not sections:
        msg = f"📁 <b>【{c_name}】</b>\n\nNo downloadable sections found in this course yet."
        inline_keyboard = {"inline_keyboard": [[{"text": "🔙 Back to Courses", "callback_data": "back_courses"}]]}
        return send_telegram_message(msg, reply_markup=inline_keyboard, chat_id=chat_id)

    buttons = []
    # Limit to top 20 sections to avoid Telegram keyboard overflow
    for idx, sec in enumerate(sections[:20]):
        display_sec = sec[:35] + ("..." if len(sec) > 35 else "")
        buttons.append([{"text": f"📂 {display_sec}", "callback_data": f"sec:{course['id']}:{idx}"}])

    buttons.append([{"text": "🔙 Back to Courses", "callback_data": "back_courses"}])
    msg = (
        f"📚 <b>【{c_name}】</b>\n\n"
        f"Select a section or topic below to view and download materials:"
    )
    return send_telegram_message(msg, reply_markup={"inline_keyboard": buttons}, chat_id=chat_id)

def send_section_resources(
    course: Dict[str, Any],
    section_name: str,
    resources: List[Dict[str, Any]],
    chat_id: Optional[str] = None
) -> bool:
    """Displays downloadable materials in a specific course section."""
    c_name = html.escape(course["full_name"])
    sec_title = html.escape(section_name)

    if not resources:
        msg = (
            f"📂 <b>【{c_name}】</b>\n"
            f"📌 <b>Section:</b> {sec_title}\n\n"
            "No downloadable lecture notes or slides in this section."
        )
        inline_keyboard = {
            "inline_keyboard": [[{"text": f"🔙 Back to {course['full_name'][:15]}...", "callback_data": f"browse:{course['id']}"}]]
        }
        return send_telegram_message(msg, reply_markup=inline_keyboard, chat_id=chat_id)

    lines = [
        f"📂 <b>【{c_name}】</b>",
        f"📌 <b>Section:</b> {sec_title}\n",
        f"Found <b>{len(resources)}</b> item(s). Tap below to send directly to your chat:\n"
    ]

    buttons = []
    for i, res in enumerate(resources[:10], 1):
        r_title = html.escape(res["title"])
        act = res.get("activity_type", "resource").upper()
        lines.append(f"{i}. 📄 <b>{r_title}</b> (<code>{act}</code>)")
        btn_label = f"📥 #{i} {res['title'][:25]}"
        buttons.append([
            {"text": btn_label, "callback_data": f"dl:{res['id']}"},
            {"text": "🔗 Web", "url": res["url"]}
        ])

    buttons.append([{"text": "🔙 Back to Course Sections", "callback_data": f"browse:{course['id']}"}])
    return send_telegram_message("\n".join(lines), reply_markup={"inline_keyboard": buttons}, chat_id=chat_id)

def send_search_results(query: str, results: List[Dict[str, Any]], chat_id: Optional[str] = None) -> bool:
    """Sends search results for course materials with instant download buttons."""
    clean_q = html.escape(query.strip())
    if not results:
        msg = (
            f"🔍 <b>【Search Results: '{clean_q}'】</b>\n\n"
            "📭 No matching materials found.\n\n"
            "💡 <i>Try searching with different keywords, e.g.:</i>\n"
            "• <code>/search lecture</code>\n"
            "• <code>/search assignment</code>\n"
            "• <code>/search tutorial</code>"
        )
        return send_telegram_message(msg, chat_id=chat_id)

    lines = [
        f"🔍 <b>【Search Results: '{clean_q}'】</b>\n",
        f"Found <b>{len(results)}</b> matching material(s):\n"
    ]
    buttons = []
    for i, r in enumerate(results[:8], 1):
        c_code = r.get("course_name", "").split()[0]
        title = html.escape(r["title"])
        sec = html.escape(r.get("section_name") or "General")
        lines.append(f"{i}. <b>[{c_code}]</b> {title}\n   ↳ 📂 <i>{sec}</i>")
        btn_label = f"📥 #{i} [{c_code}] {r['title'][:20]}"
        buttons.append([
            {"text": btn_label, "callback_data": f"dl:{r['id']}"},
            {"text": "🔗 Open", "url": r["url"]}
        ])

    return send_telegram_message("\n".join(lines), reply_markup={"inline_keyboard": buttons}, chat_id=chat_id)

def send_system_status(stats: Dict[str, Any], is_logged_in: bool = True, chat_id: Optional[str] = None) -> bool:
    """Sends detailed bot status."""
    last_check = stats.get("last_checked") or "Never checked yet"
    auth_str = "🟢 Active & Valid" if is_logged_in else "🔴 Expired (Run `python main.py --login`)"
    
    msg = (
        "⚙️ <b>【SpectrumBot System Status】</b>\n\n"
        f"🔐 <b>SPeCTRUM Session:</b> {auth_str}\n"
        f"⏱️ <b>Check Interval:</b> Every {config.CHECK_INTERVAL_MINUTES} minutes\n"
        f"🕒 <b>Last Checked:</b> {last_check}\n\n"
        f"📊 <b>Database Statistics:</b>\n"
        f"• Monitored Courses: {stats.get('courses_count', 0)}\n"
        f"• Total Resources Tracked: {stats.get('resources_count', 0)}\n"
        f"• Total Announcements Tracked: {stats.get('announcements_count', 0)}"
    )
    return send_telegram_message(msg, reply_markup=MAIN_KEYBOARD, chat_id=chat_id)

def send_help_message(chat_id: Optional[str] = None) -> bool:
    """Sends help instructions."""
    msg = (
        "❓ <b>【SpectrumBot Help Guide】</b>\n\n"
        "You can tap the buttons below or send any of the following commands:\n"
        "• <code>/search &lt;keyword&gt;</code>: Search any slide or lecture note (e.g. <code>/search lecture 1</code>)\n"
        "• <code>/courses</code> or <b>📚 My Courses</b>: View courses & browse past materials\n"
        "• <code>/check</code> or <b>🔍 Check Now</b>: Check SPeCTRUM right away\n"
        "• <code>/status</code> or <b>⚙️ Status</b>: View bot & session status\n"
        "• <code>/login</code>: Remotely refresh session or receive login QR code on Telegram\n"
        "• <code>/start</code>: Re-display the menu keyboard\n\n"
        "💡 <i>Tip: Any newly uploaded slides or announcements will be sent here automatically with direct download buttons.</i>"
    )
    return send_telegram_message(msg, reply_markup=MAIN_KEYBOARD, chat_id=chat_id)
