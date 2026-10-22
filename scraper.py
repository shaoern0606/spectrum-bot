import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, BrowserContext, Page
import config

logger = logging.getLogger(__name__)

class SpectrumScraper:
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.context: Optional[BrowserContext] = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    def start(self):
        if not config.AUTH_STATE_FILE.exists():
            raise FileNotFoundError(
                f"Session file {config.AUTH_STATE_FILE} not found. Please run `python main.py --login` first to authenticate."
            )
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"]
        )
        self.context = self.browser.new_context(
            storage_state=str(config.AUTH_STATE_FILE),
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

    def stop(self):
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

    def check_auth_valid(self, page: Page) -> tuple[bool, bool]:
        """
        Verifies if the current session is still logged into Spectrum, auto-renewing if needed.
        Returns: (is_authenticated: bool, is_maintenance: bool)
        """
        try:
            page.goto(f"{config.SPECTRUM_BASE_URL}/my/", wait_until="domcontentloaded", timeout=30000)
            url = page.url.lower()
            
            # Check for genuine UM ICT maintenance / service offline page (title or dedicated maintenance container)
            title = page.title().lower() if page else ""
            body_text = page.locator("body").inner_text().lower() if page.locator("body").count() > 0 else ""
            if ("service offline" in title or "maintenance" in title or "penyelenggaraan" in title) or ("portal sedang diselenggara" in body_text or "under maintenance" in body_text):
                logger.warning("🚧 UM SPeCTRUM is currently offline for scheduled ICT maintenance.")
                return False, True

            has_logout = page.locator("a[href*='login/logout.php']").count() > 0
            is_body_loggedin = page.locator("body.loggedin").count() > 0

            if not ("login" in url or "microsoftonline" in url) and (has_logout or is_body_loggedin):
                return True, False

            logger.info("Session appears unauthenticated. Attempting automatic silent SSO refresh...")
            if self.attempt_silent_sso_renew(page):
                logger.info("✅ Silent SSO refresh succeeded! New session state saved.")
                return True, False

            return False, False
        except Exception as e:
            logger.error(f"Error checking login session: {e}")
            return False, False

    def attempt_silent_sso_renew(self, page: Page) -> bool:
        """Navigates through SSO login to seamlessly refresh MoodleSession without user interaction."""
        try:
            page.goto(f"{config.SPECTRUM_BASE_URL}/login/index.php", wait_until="networkidle", timeout=30000)
            has_logout = page.locator("a[href*='login/logout.php']").count() > 0
            is_body_loggedin = page.locator("body.loggedin").count() > 0
            current_url = page.url.lower()

            if not ("login" in current_url or "microsoftonline" in current_url) and (has_logout or is_body_loggedin):
                if self.context:
                    self.context.storage_state(path=str(config.AUTH_STATE_FILE))
                return True
            return False
        except Exception as e:
            logger.warning(f"Silent SSO refresh attempt failed: {e}")
            return False

    def get_enrolled_courses(self, page: Page) -> List[Dict[str, str]]:
        """Scrapes enrolled courses from the user's My Courses page (/my/courses.php)."""
        logger.info("Fetching enrolled courses list from SPeCTRUM...")
        
        # UM SPeCTRUM / Moodle 4 lists all enrolled courses under /my/courses.php
        target_url = f"{config.SPECTRUM_BASE_URL}/my/courses.php"
        try:
            page.goto(target_url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(2000)
        except Exception:
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_selector(".dashboard-card, .course-info-container, .card", timeout=8000)
            except Exception:
                page.goto(f"{config.SPECTRUM_BASE_URL}/my/", wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(3000)

        soup = BeautifulSoup(page.content(), "html.parser")
        courses = {}
        course_link_pattern = re.compile(r"/course/view\.php\?id=(\d+)")

        # 1. Search course cards for titles and links
        cards = soup.find_all(class_=re.compile(r"(course-card|dashboard-card|card|course-info-container)"))
        for card in cards:
            link = card.find("a", href=course_link_pattern)
            if not link:
                continue
            c_id = course_link_pattern.search(link["href"]).group(1)
            
            # Find title element
            title_elem = card.find(class_=re.compile(r"coursename|course-name|course-title")) or card.find(["h3", "h4", "h5", "h6"])
            raw_title = title_elem.get_text(strip=True) if title_elem else link.get_text(strip=True)
            
            # Remove "Course name" screen-reader prefix
            raw_title = re.sub(r"^Course name\s*", "", raw_title, flags=re.IGNORECASE)
            raw_title = re.sub(r"\s+", " ", raw_title).strip()
            
            if c_id not in courses and raw_title and raw_title.lower() != "view course" and not raw_title.isdigit():
                courses[c_id] = {
                    "id": c_id,
                    "full_name": raw_title,
                    "url": f"{config.SPECTRUM_BASE_URL}/course/view.php?id={c_id}"
                }

        # 2. Fallback to any remaining direct course links on page
        for a in soup.find_all("a", href=course_link_pattern):
            href = a.get("href", "")
            match = course_link_pattern.search(href)
            if not match:
                continue
            c_id = match.group(1)
            if c_id not in courses:
                title = a.get_text(strip=True)
                title = re.sub(r"^Course name\s*", "", title, flags=re.IGNORECASE)
                title = re.sub(r"\s+", " ", title).strip()
                if title and title.lower() != "view course" and not title.isdigit():
                    courses[c_id] = {
                        "id": c_id,
                        "full_name": title,
                        "url": f"{config.SPECTRUM_BASE_URL}/course/view.php?id={c_id}"
                    }

        course_list = list(courses.values())
        logger.info(f"Scanned {len(course_list)} enrolled courses from SPeCTRUM.")

        # Apply blacklist filter (e.g. LEAP, Turnitin)
        if config.EXCLUDED_COURSES:
            course_list = [
                c for c in course_list
                if not any(kw.lower() in c["full_name"].lower() or kw.lower() == c["id"].lower() for kw in config.EXCLUDED_COURSES)
            ]

        # Apply whitelist filter if configured
        if config.MONITORED_COURSES:
            filtered = []
            for c in course_list:
                for kw in config.MONITORED_COURSES:
                    if kw.lower() in c["id"].lower() or kw.lower() in c["full_name"].lower():
                        filtered.append(c)
                        break
            logger.info(f"Monitoring {len(filtered)} courses after applying whitelist filter.")
            return filtered

        logger.info(f"Monitoring {len(course_list)} courses after excluding blacklisted portals.")
        return course_list

    def scrape_course_content(self, page: Page, course: Dict[str, str]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Scrapes all course resources and forum announcements for a specific course.
        Returns (resources_list, announcements_list).
        """
        c_id = course["id"]
        c_name = course["full_name"]
        logger.info(f"Scraping course '{c_name}' (ID: {c_id})...")
        
        try:
            page.goto(course["url"], wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(2000)
        except Exception as e:
            logger.error(f"Failed to open course page {course['url']}: {e}")
            return [], []

        soup = BeautifulSoup(page.content(), "html.parser")
        resources = []
        forum_links = []

        # Find all course sections
        sections = soup.find_all(["li", "div"], class_=re.compile(r"\bsection\b"))
        if not sections:
            # Fallback to entire page if section containers aren't cleanly segmented
            sections = [soup]

        seen_sec_ids = set()
        for sec in sections:
            # Extract section name
            sec_header = sec.find(["h3", "h4", "span"], class_=re.compile(r"sectionname|section-title"))
            section_name = sec_header.get_text(strip=True) if sec_header else "General"
            section_name = re.sub(r"\s+", " ", section_name).strip()

            # Check section link or ID
            sec_link_elem = sec.find("a", href=re.compile(r"course/section\.php\?id=(\d+)"))
            sec_url = sec_link_elem.get("href", "") if sec_link_elem else course["url"]
            sec_id_match = re.search(r"id=(\d+)", sec_url)
            sec_id_str = sec_id_match.group(1) if sec_id_match else (sec.get("id", "") or "0")

            # Extract Section Summary / Weekly Instructions
            if sec_id_str not in seen_sec_ids:
                seen_sec_ids.add(sec_id_str)
                summary_elem = sec.find(class_=re.compile(r"\bsummarytext\b|\bsummary\b"))
                if summary_elem:
                    for tag in summary_elem.find_all(["script", "style"]):
                        tag.decompose()
                    summary_raw = summary_elem.get_text("\n", strip=True)
                    summary_clean = re.sub(r"\n\s*\n+", "\n", summary_raw).strip()
                    if len(summary_clean) >= 25:
                        import hashlib
                        content_hash = hashlib.md5(summary_clean.encode("utf-8")).hexdigest()[:10]
                        first_line = summary_clean.split("\n")[0].strip()
                        if len(first_line) > 50:
                            first_line = first_line[:47] + "..."
                        sec_title = f"Guide: {first_line}" if first_line else f"Instructions for {section_name}"
                        item_id = f"{c_id}_sec_{sec_id_str}_{content_hash}"
                        resources.append({
                            "id": item_id,
                            "course_id": c_id,
                            "section_name": section_name,
                            "title": sec_title,
                            "activity_type": "instruction",
                            "url": sec_url or course["url"],
                            "content_snippet": summary_clean[:400]
                        })

            # Find all activities/resources in this section
            activities = sec.find_all(["li", "div"], class_=re.compile(r"\bactivity\b"))
            for act in activities:
                # Check activity type from class list (e.g. modtype_resource, modtype_folder, etc.)
                classes = " ".join(act.get("class", []))
                act_type = "resource"
                type_match = re.search(r"modtype_(\w+)", classes)
                if type_match:
                    act_type = type_match.group(1)

                link_elem = act.find("a", href=re.compile(r"/mod/"))
                if not link_elem:
                    continue

                act_url = link_elem.get("href", "")
                
                # Check for announcement/news forum
                if "forum" in act_type:
                    forum_links.append((act_url, link_elem.get_text(strip=True)))
                    # Forums are handled in detail below

                # Clean activity title
                # Remove Moodle's screen-reader hidden span elements like <span class="accesshide">File</span>
                for hide in act.find_all(class_="accesshide"):
                    hide.decompose()

                title_elem = act.find(class_=re.compile(r"instancename|activityname")) or link_elem
                title = re.sub(r"\s+", " ", title_elem.get_text(strip=True)).strip()

                # Determine unique module ID
                mod_id_match = re.search(r"id=(\d+)", act_url)
                if not mod_id_match:
                    mod_id_match = re.search(r"module-(\d+)", act.get("id", ""))
                
                if not mod_id_match or not title:
                    continue

                item_id = f"{c_id}_mod_{mod_id_match.group(1)}"
                resources.append({
                    "id": item_id,
                    "course_id": c_id,
                    "section_name": section_name,
                    "title": title,
                    "activity_type": act_type,
                    "url": act_url,
                })

        # Comprehensive fallback sweep: ensure no assignment or quiz is missed anywhere on the course page
        existing_res_ids = {r["id"] for r in resources}
        for link in soup.find_all("a", href=re.compile(r"/mod/(assign|quiz)/view\.php\?id=(\d+)")):
            href = link.get("href", "")
            m = re.search(r"id=(\d+)", href)
            if not m:
                continue
            mod_id = m.group(1)
            item_id = f"{c_id}_mod_{mod_id}"
            if item_id in existing_res_ids:
                continue
            act_type = "quiz" if "/mod/quiz/" in href else "assign"
            raw_title = link.get_text(" ", strip=True)
            clean_t = re.sub(r"\s+(?:Assignment|Quiz)$", "", raw_title, flags=re.IGNORECASE).strip()
            if not clean_t or clean_t.isdigit():
                continue
            existing_res_ids.add(item_id)
            resources.append({
                "id": item_id,
                "course_id": c_id,
                "section_name": "Course Activities",
                "title": clean_t,
                "activity_type": act_type,
                "url": href
            })

        # Now scrape announcements from detected forum links
        announcements = []
        seen_forum_urls = set()
        for f_url, f_name in forum_links:
            if f_url in seen_forum_urls:
                continue
            seen_forum_urls.add(f_url)

            # We specifically look for "announcement" or "news" or general forums
            is_announcement = any(k in f_name.lower() for k in ["announcement", "news", "notis", "pengumuman", "general"])
            if not is_announcement and len(forum_links) > 2:
                # If there are many discussion forums, only inspect the main announcement forum
                continue

            forum_items = self._scrape_forum_topics(page, c_id, f_url)
            announcements.extend(forum_items)

        # Deduplicate announcements by ID
        unique_announcements = []
        seen_ann_ids = set()
        for ann in announcements:
            if ann["id"] not in seen_ann_ids:
                seen_ann_ids.add(ann["id"])
                unique_announcements.append(ann)

        # Deduplicate resources by ID
        unique_resources = []
        seen_res_ids = set()
        for res in resources:
            if res["id"] not in seen_res_ids:
                seen_res_ids.add(res["id"])
                unique_resources.append(res)

        return unique_resources, unique_announcements

    def _scrape_forum_topics(self, page: Page, course_id: str, forum_url: str) -> List[Dict[str, Any]]:
        """Scrapes topics/posts from a Moodle forum."""
        topics = []
        try:
            page.goto(forum_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1500)
            soup = BeautifulSoup(page.content(), "html.parser")

            # Moodle forum table rows
            rows = soup.find_all("tr", class_=re.compile(r"\bdiscussion\b"))
            for r in rows:
                topic_link = r.find("a", href=re.compile(r"discuss\.php\?d=(\d+)"))
                if not topic_link:
                    continue

                d_match = re.search(r"discuss\.php\?d=(\d+)", topic_link.get("href", ""))
                if not d_match:
                    continue

                d_id = d_match.group(1)
                topic_title = topic_link.get_text(strip=True)

                # Check for created time
                time_created_elem = r.find("time", id=re.compile(r"time-created")) or r.find("time")
                posted_time = time_created_elem.get_text(strip=True) if time_created_elem else ""

                # Author: In Moodle discussion tables, starter author is in the first author cell
                author = "Instructor"
                author_elem = r.find(class_=re.compile(r"\bauthor\b|\buser\b"))
                if author_elem:
                    user_link = author_elem.find("a", href=re.compile(r"user/view\.php"))
                    if user_link:
                        author = user_link.get_text(strip=True)
                    else:
                        raw_auth = author_elem.get_text(" ", strip=True)
                        if posted_time and posted_time in raw_auth:
                            raw_auth = raw_auth.replace(posted_time, "")
                        author = re.sub(r"[\s\.\·\-\,]+$", "", raw_auth).strip()

                # 1. Starter post
                topics.append({
                    "id": f"{course_id}_discuss_{d_id}",
                    "course_id": course_id,
                    "title": topic_title,
                    "author": author,
                    "posted_time": posted_time,
                    "content_snippet": "",
                    "url": topic_link.get("href", "")
                })

                # 2. Check for replies or thread updates
                replies_count = 0
                for td in r.find_all("td"):
                    td_text = td.get_text(strip=True)
                    if td_text.isdigit():
                        try:
                            replies_count = int(td_text)
                            break
                        except ValueError:
                            pass

                last_post_link = r.find("a", href=re.compile(r"parent=(\d+)"))
                time_modified_elem = r.find("time", id=re.compile(r"time-modified"))

                if replies_count > 0 and last_post_link:
                    parent_match = re.search(r"parent=(\d+)", last_post_link.get("href", ""))
                    last_post_id = parent_match.group(1) if parent_match else ""
                    last_time = last_post_link.get("title", "") or (time_modified_elem.get_text(strip=True) if time_modified_elem else "")
                    
                    # Extract latest post author from the last post cell
                    last_td = last_post_link.find_parent("td")
                    last_author = author
                    if last_td:
                        auth_div = last_td.find(class_=re.compile(r"author-info|author"))
                        if auth_div:
                            truncate_div = auth_div.find(class_=re.compile(r"text-truncate"))
                            if truncate_div:
                                last_author = re.sub(r"[\s\.\·\-\,]+$", "", truncate_div.get_text(strip=True)).strip()

                    reply_item_id = f"{course_id}_discuss_{d_id}_reply_{last_post_id}" if last_post_id else f"{course_id}_discuss_{d_id}_updated_{last_time}"
                    topics.append({
                        "id": reply_item_id,
                        "course_id": course_id,
                        "title": f"Update: {topic_title}",
                        "author": last_author,
                        "posted_time": last_time or posted_time,
                        "content_snippet": "",
                        "url": last_post_link.get("href", "")
                    })
        except Exception as e:
            logger.warning(f"Error scraping forum discussions {forum_url}: {e}")

        return topics

    def check_quiz_status(self, page: Page, quiz_url: str) -> tuple[str, str, Optional[int], str]:
        """
        Visits quiz page and extracts:
        (submission_status, time_remaining, due_timestamp, due_date_str)
        """
        try:
            page.goto(quiz_url, wait_until="domcontentloaded", timeout=25000)
            soup = BeautifulSoup(page.content(), "html.parser")

            sub_status = "pending"
            time_remaining = ""
            due_str = ""
            due_ts = None

            # 1. Look for close/due time text
            for box in soup.find_all(class_=re.compile(r"box|quizinfo|generalbox")):
                text = box.get_text(" ", strip=True)
                close_match = re.search(r"(?:closes|close on|due:?)\s*(?:on\s*)?([A-Za-z]+,?\s+\d+\s+[A-Za-z]+(?:\s+\d{4})?,?\s+\d+:\d+\s*(?:[AP]M)?)", text, flags=re.IGNORECASE)
                if close_match:
                    due_str = close_match.group(1).strip()
                    break

            if due_str:
                clean_due = re.sub(r"\s+", " ", due_str).strip()
                for fmt in [
                    "%A, %d %B %Y, %I:%M %p",
                    "%a, %d %b %Y, %I:%M %p",
                    "%d %B %Y, %I:%M %p",
                    "%d %b %Y, %I:%M %p",
                    "%A, %d %B %Y",
                    "%d %B %Y"
                ]:
                    try:
                        dt = datetime.strptime(clean_due, fmt)
                        due_ts = int(dt.timestamp())
                        break
                    except ValueError:
                        pass

            # 2. Check previous attempts summary
            table = soup.find("table", class_=re.compile(r"generaltable|quizattemptsummary"))
            if table:
                for tr in table.find_all("tr")[1:]:
                    row_txt = tr.get_text(" ", strip=True).lower()
                    if "finished" in row_txt or "submitted" in row_txt:
                        sub_status = "submitted"
                        break

            return sub_status, time_remaining, due_ts, due_str
        except Exception as e:
            logger.warning(f"Error checking quiz {quiz_url}: {e}")
            return "pending", "", None, ""

    def check_assignment_submission_status(self, page: Page, assign_url: str) -> tuple[str, str, Optional[int], str]:
        """
        Visits assignment or quiz page and extracts:
        (submission_status, time_remaining, due_timestamp, due_date_str)
        """
        if "/mod/quiz/" in assign_url:
            return self.check_quiz_status(page, assign_url)
        try:
            page.goto(assign_url, wait_until="domcontentloaded", timeout=25000)
            soup = BeautifulSoup(page.content(), "html.parser")
            
            sub_status = "pending"
            time_remaining = ""
            due_str = ""
            due_ts = None

            # Extract Due Date from <div class="date-item">
            for el in soup.find_all(string=re.compile(r"Due:", re.IGNORECASE)):
                parent = el.parent
                if parent:
                    container = parent.parent if parent.name in ["span", "b", "strong"] else parent
                    raw_text = container.get_text(" ", strip=True)
                    due_str = re.sub(r"^Due:\s*", "", raw_text, flags=re.IGNORECASE).strip()
                    break

            # Parse Due Date string to epoch timestamp
            if due_str:
                clean_due = re.sub(r"\s+", " ", due_str).strip()
                for fmt in [
                    "%A, %d %B %Y, %I:%M %p",
                    "%a, %d %b %Y, %I:%M %p",
                    "%d %B %Y, %I:%M %p",
                    "%d %b %Y, %I:%M %p",
                    "%A, %d %B %Y",
                    "%d %B %Y"
                ]:
                    try:
                        dt = datetime.strptime(clean_due, fmt)
                        due_ts = int(dt.timestamp())
                        break
                    except ValueError:
                        pass

            # Extract Submission status & time remaining from table
            table = soup.find("table", class_=re.compile(r"generaltable|submissionsummarytable"))
            if table:
                for tr in table.find_all("tr"):
                    cells = tr.find_all(["th", "td"])
                    if len(cells) >= 2:
                        label = cells[0].get_text(strip=True).lower()
                        val = cells[-1].get_text(strip=True)

                        if "submission status" in label:
                            v_lower = val.lower()
                            if "submitted" in v_lower and "no submit" not in v_lower and "not submitted" not in v_lower:
                                sub_status = "submitted"
                            elif "no attempt" in v_lower or "no submission" in v_lower or "not submitted" in v_lower:
                                sub_status = "pending"
                            else:
                                sub_status = val
                        elif "time remaining" in label:
                            time_remaining = val
                            if "overdue" in val.lower() and sub_status != "submitted":
                                sub_status = "overdue"

            return sub_status, time_remaining, due_ts, due_str
        except Exception as e:
            logger.warning(f"Error checking assignment {assign_url}: {e}")
            return "pending", "", None, ""

    def scrape_upcoming_deadlines(self, page: Page, courses_map: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
        """
        Scrapes upcoming assignments and quizzes from the calendar page:
        https://spectrum.um.edu.my/calendar/view.php?view=upcoming
        """
        logger.info("Scraping upcoming deadlines from SPeCTRUM Calendar...")
        target_url = f"{config.SPECTRUM_BASE_URL}/calendar/view.php?view=upcoming"
        try:
            page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)
        except Exception as e:
            logger.error(f"Failed to load calendar page: {e}")
            return []

        soup = BeautifulSoup(page.content(), "html.parser")
        events = soup.find_all("div", class_=re.compile(r"\bevent\b"))
        deadlines = []

        for ev in events:
            comp = ev.get("data-event-component", "")
            if "assign" not in comp and "quiz" not in comp:
                continue

            event_id = ev.get("data-event-id")
            course_id = ev.get("data-course-id", "")
            event_title = ev.get("data-event-title") or ""
            clean_title = re.sub(r"\s+is due\b", "", event_title, flags=re.IGNORECASE).strip()

            link_elem = ev.find("a", href=re.compile(r"/mod/(assign|quiz)/view\.php\?id=(\d+)"))
            if not link_elem:
                continue
            activity_url = link_elem.get("href", "")
            
            m_id = re.search(r"id=(\d+)", activity_url)
            prefix = "quiz" if "quiz" in comp else "assign"
            item_id = f"{prefix}_{m_id.group(1)}" if m_id else f"event_{event_id}"

            due_ts = None
            date_span = ev.find("span", attrs={"data-timestamp": True})
            if date_span and date_span.get("data-timestamp"):
                try:
                    due_ts = int(date_span.get("data-timestamp"))
                except ValueError:
                    pass

            if not due_ts:
                time_link = ev.find("a", href=re.compile(r"time=(\d+)"))
                if time_link:
                    t_match = re.search(r"time=(\d+)", time_link.get("href", ""))
                    if t_match:
                        due_ts = int(t_match.group(1))

            date_text = date_span.get_text(strip=True) if date_span else ""

            course_name = (courses_map.get(course_id) if courses_map else "") or ""
            if not course_name:
                c_link = ev.find("a", href=re.compile(r"/course/view\.php\?id="))
                if c_link:
                    course_name = c_link.get_text(strip=True)

            deadlines.append({
                "id": item_id,
                "course_id": course_id,
                "course_name": course_name or f"Course {course_id}",
                "title": clean_title or "Assignment",
                "url": activity_url,
                "due_timestamp": due_ts or 0,
                "due_time_str": date_text
            })

        logger.info(f"Discovered {len(deadlines)} deadline events on calendar. Checking submission statuses...")
        for d in deadlines:
            sub_status, time_rem, page_due_ts, page_due_str = self.check_assignment_submission_status(page, d["url"])
            d["submission_status"] = sub_status
            d["time_remaining_str"] = time_rem
            if page_due_ts and not d.get("due_timestamp"):
                d["due_timestamp"] = page_due_ts
            if page_due_str:
                d["due_time_str"] = page_due_str

        return deadlines

    def scrape_course_assignments(self, page: Page, course: Dict[str, str], task_resources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Inspects assignment and quiz activities found inside a course to check their due dates and submission statuses.
        """
        import storage
        results = []
        for r in task_resources:
            r_url = r.get("url", "")
            if not r_url or ("/mod/assign/" not in r_url and "/mod/quiz/" not in r_url):
                continue

            m_id = re.search(r"id=(\d+)", r_url)
            prefix = "quiz" if "/mod/quiz/" in r_url else "assign"
            assign_id = f"{prefix}_{m_id.group(1)}" if m_id else r["id"]

            # If already recorded as submitted in database, reuse cached info
            cached = storage.get_assignment_by_id(assign_id)
            if cached and cached.get("submission_status") == "submitted":
                results.append(cached)
                continue

            sub_status, time_rem, due_ts, due_str = self.check_assignment_submission_status(page, r_url)
            if not due_ts and not due_str:
                continue

            # Skip past years
            if due_ts:
                dt_obj = datetime.fromtimestamp(due_ts)
                if dt_obj.year < datetime.now().year:
                    continue

            item = {
                "id": assign_id,
                "course_id": course["id"],
                "course_name": course["full_name"],
                "title": r["title"],
                "url": r_url,
                "due_timestamp": due_ts or 0,
                "due_time_str": due_str or "",
                "submission_status": sub_status,
                "time_remaining_str": time_rem
            }
            results.append(item)
            storage.upsert_assignment(item)
        return results
