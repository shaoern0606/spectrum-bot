import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import config

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    """Initializes the SQLite database tables."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS courses (
                id TEXT PRIMARY KEY,
                full_name TEXT NOT NULL,
                url TEXT NOT NULL,
                last_checked TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS resources (
                id TEXT PRIMARY KEY,
                course_id TEXT NOT NULL,
                section_name TEXT,
                title TEXT NOT NULL,
                activity_type TEXT,
                url TEXT NOT NULL,
                first_seen TIMESTAMP NOT NULL,
                FOREIGN KEY (course_id) REFERENCES courses (id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS announcements (
                id TEXT PRIMARY KEY,
                course_id TEXT NOT NULL,
                title TEXT NOT NULL,
                author TEXT,
                posted_time TEXT,
                content_snippet TEXT,
                url TEXT NOT NULL,
                first_seen TIMESTAMP NOT NULL,
                FOREIGN KEY (course_id) REFERENCES courses (id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS subscribers (
                chat_id TEXT PRIMARY KEY,
                first_name TEXT,
                username TEXT,
                joined_at TIMESTAMP NOT NULL,
                is_approved INTEGER DEFAULT 0
            )
        """)
        # Migration for existing database: add is_approved column if missing
        cursor.execute("PRAGMA table_info(subscribers)")
        cols = [r[1] for r in cursor.fetchall()]
        if "is_approved" not in cols:
            cursor.execute("ALTER TABLE subscribers ADD COLUMN is_approved INTEGER DEFAULT 0")
        conn.commit()

def is_database_empty() -> bool:
    """Check if the database currently has no records (first run detection)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM resources")
        res_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM announcements")
        ann_count = cursor.fetchone()[0]
        return (res_count + ann_count) == 0

def is_course_new(course_id: str) -> bool:
    """Check if this course is new to the database."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM courses WHERE id = ?", (course_id,))
        return cursor.fetchone()[0] == 0

def upsert_course(course_id: str, full_name: str, url: str) -> None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO courses (id, full_name, url, last_checked)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                full_name = excluded.full_name,
                url = excluded.url,
                last_checked = excluded.last_checked
        """, (course_id, full_name, url, datetime.now()))
        conn.commit()

def get_resource_by_id(res_id: str) -> Optional[Dict[str, Any]]:
    """Fetches a single resource by its ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM resources WHERE id = ?", (res_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def has_instructions_baseline() -> bool:
    """Checks if instruction-type items have ever been recorded in resources."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM resources WHERE activity_type = 'instruction'")
        return cursor.fetchone()[0] > 0

def is_course_instructions_initialized(course_id: str) -> bool:
    """Checks if instruction-type items have ever been recorded for this specific course."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM resources WHERE course_id = ? AND activity_type = 'instruction'", (str(course_id),))
        return cursor.fetchone()[0] > 0

def filter_new_resources(course_id: str, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Returns only items that are not yet recorded in the database."""
    if not items:
        return []
    with get_connection() as conn:
        cursor = conn.cursor()
        ids = [item["id"] for item in items]
        placeholders = ",".join("?" for _ in ids)
        cursor.execute(f"SELECT id FROM resources WHERE id IN ({placeholders})", ids)
        existing_ids = {row[0] for row in cursor.fetchall()}
    
    seen = set()
    new_items = []
    for item in items:
        if item["id"] not in existing_ids and item["id"] not in seen:
            seen.add(item["id"])
            new_items.append(item)
    return new_items

def save_resources(items: List[Dict[str, Any]]) -> None:
    if not items:
        return
    with get_connection() as conn:
        cursor = conn.cursor()
        now = datetime.now()
        for item in items:
            cursor.execute("""
                INSERT OR IGNORE INTO resources 
                (id, course_id, section_name, title, activity_type, url, first_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                item["id"],
                item["course_id"],
                item.get("section_name", "General"),
                item["title"],
                item.get("activity_type", "resource"),
                item["url"],
                now
            ))
        conn.commit()

def filter_new_announcements(course_id: str, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Returns only announcement posts that are not yet recorded."""
    if not items:
        return []
    with get_connection() as conn:
        cursor = conn.cursor()
        ids = [item["id"] for item in items]
        placeholders = ",".join("?" for _ in ids)
        cursor.execute(f"SELECT id FROM announcements WHERE id IN ({placeholders})", ids)
        existing_ids = {row[0] for row in cursor.fetchall()}
    
    seen = set()
    new_items = []
    for item in items:
        if item["id"] not in existing_ids and item["id"] not in seen:
            seen.add(item["id"])
            new_items.append(item)
    return new_items

def save_announcements(items: List[Dict[str, Any]]) -> None:
    if not items:
        return
    with get_connection() as conn:
        cursor = conn.cursor()
        now = datetime.now()
        for item in items:
            cursor.execute("""
                INSERT OR IGNORE INTO announcements
                (id, course_id, title, author, posted_time, content_snippet, url, first_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item["id"],
                item["course_id"],
                item["title"],
                item.get("author", "Instructor"),
                item.get("posted_time", ""),
                item.get("content_snippet", ""),
                item["url"],
                now
            ))
        conn.commit()

def get_courses_summary() -> List[Dict[str, Any]]:
    """Returns list of courses with their resource and announcement counts."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                c.id, c.full_name, c.url, c.last_checked,
                COUNT(DISTINCT r.id) as resource_count,
                COUNT(DISTINCT a.id) as announcement_count
            FROM courses c
            LEFT JOIN resources r ON c.id = r.course_id
            LEFT JOIN announcements a ON c.id = a.course_id
            GROUP BY c.id
            ORDER BY c.full_name ASC
        """)
        return [dict(row) for row in cursor.fetchall()]

def get_system_stats() -> Dict[str, Any]:
    """Returns overall summary statistics."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM courses")
        c_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM resources")
        r_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM announcements")
        a_count = cursor.fetchone()[0]
        cursor.execute("SELECT MAX(last_checked) FROM courses")
        last_check = cursor.fetchone()[0]
        return {
            "courses_count": c_count,
            "resources_count": r_count,
            "announcements_count": a_count,
            "last_checked": last_check
        }

def remove_courses_by_keywords(keywords: List[str]) -> List[str]:
    """Removes courses and associated records matching keywords."""
    removed = []
    with get_connection() as conn:
        cursor = conn.cursor()
        for kw in keywords:
            cursor.execute("SELECT id, full_name FROM courses WHERE full_name LIKE ? OR id = ?", (f"%{kw}%", kw))
            rows = cursor.fetchall()
            for r in rows:
                c_id, full_name = r[0], r[1]
                if full_name not in removed:
                    removed.append(full_name)
                    cursor.execute("DELETE FROM resources WHERE course_id = ?", (c_id,))
                    cursor.execute("DELETE FROM announcements WHERE course_id = ?", (c_id,))
                    cursor.execute("DELETE FROM courses WHERE id = ?", (c_id,))
        conn.commit()
    return removed

def is_user_approved(chat_id: str) -> bool:
    """Checks whether a user is approved to access the bot."""
    cid = str(chat_id).strip()
    if config.TELEGRAM_CHAT_ID and cid == str(config.TELEGRAM_CHAT_ID).strip():
        return True
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT is_approved FROM subscribers WHERE chat_id = ?", (cid,))
        row = cursor.fetchone()
        return bool(row and row[0] == 1)

def add_subscriber(chat_id: str, first_name: str = "", username: str = "", is_approved: int = 0) -> bool:
    """Adds a subscriber, defaulting to pending (is_approved=0) unless admin or specified."""
    cid = str(chat_id).strip()
    if config.TELEGRAM_CHAT_ID and cid == str(config.TELEGRAM_CHAT_ID).strip():
        is_approved = 1
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO subscribers (chat_id, first_name, username, joined_at, is_approved)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                first_name = excluded.first_name,
                username = excluded.username
        """, (cid, first_name, username, datetime.now(), is_approved))
        conn.commit()
        return True

def approve_subscriber(chat_id: str) -> bool:
    """Approves a subscriber."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE subscribers SET is_approved = 1 WHERE chat_id = ?", (str(chat_id).strip(),))
        conn.commit()
        return cursor.rowcount > 0

def block_subscriber(chat_id: str) -> bool:
    """Blocks/revokes a subscriber."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE subscribers SET is_approved = 0 WHERE chat_id = ?", (str(chat_id).strip(),))
        conn.commit()
        return cursor.rowcount > 0

def remove_subscriber(chat_id: str) -> bool:
    """Deletes a subscriber from the database."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM subscribers WHERE chat_id = ?", (str(chat_id).strip(),))
        conn.commit()
        return cursor.rowcount > 0

def get_all_subscribers() -> List[str]:
    """Returns list of all APPROVED subscribed chat IDs."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT chat_id FROM subscribers WHERE is_approved = 1")
        rows = [str(r[0]) for r in cursor.fetchall()]
        if config.TELEGRAM_CHAT_ID and str(config.TELEGRAM_CHAT_ID) not in rows:
            rows.append(str(config.TELEGRAM_CHAT_ID))
        return rows

def list_subscribers_status() -> List[Dict[str, Any]]:
    """Returns all subscribers with their approval status."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT chat_id, first_name, username, joined_at, is_approved FROM subscribers ORDER BY joined_at ASC")
        return [dict(r) for r in cursor.fetchall()]

def get_course_by_id(course_id: str) -> Optional[Dict[str, Any]]:
    """Fetches course info by its ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM courses WHERE id = ?", (str(course_id),))
        row = cursor.fetchone()
        return dict(row) if row else None

def search_resources(query: str, limit: int = 8) -> List[Dict[str, Any]]:
    """Searches resources by keyword in title or section name, joining course name."""
    with get_connection() as conn:
        cursor = conn.cursor()
        pattern = f"%{query.strip()}%"
        cursor.execute("""
            SELECT r.*, c.full_name as course_name 
            FROM resources r
            JOIN courses c ON r.course_id = c.id
            WHERE r.title LIKE ? OR r.section_name LIKE ?
            ORDER BY r.first_seen DESC
            LIMIT ?
        """, (pattern, pattern, limit))
        return [dict(row) for row in cursor.fetchall()]

def get_course_sections(course_id: str) -> List[str]:
    """Returns distinct section names for a given course."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT section_name 
            FROM resources 
            WHERE course_id = ? AND section_name IS NOT NULL AND section_name != ''
            ORDER BY rowid ASC
        """, (str(course_id),))
        return [r[0] for r in cursor.fetchall()]

def get_resources_by_course_and_section(course_id: str, section_name: str, limit: int = 15) -> List[Dict[str, Any]]:
    """Returns resources in a specific section of a course."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM resources 
            WHERE course_id = ? AND section_name = ?
            ORDER BY rowid ASC
            LIMIT ?
        """, (str(course_id), section_name, limit))
        return [dict(row) for row in cursor.fetchall()]

