import logging
import re
import urllib.parse
from typing import Any, Dict, List
from bs4 import BeautifulSoup
from playwright.sync_api import Page
import config

logger = logging.getLogger(__name__)

TEAMS_URL = "https://teams.cloud.microsoft/"

ACADEMIC_PREFIXES = ("DR.", "DR ", "PROF", "ASSOC PROF", "MADAM", "TS.", "ENCIK", "PUAN", "SIR ")


def _is_monitored_team(team: Dict[str, Any]) -> bool:
    if team.get("isArchived"):
        return False
    name = (team.get("displayName") or "").strip()
    if not name:
        return False
    name_lower = name.lower()

    if any(exc.lower() in name_lower for exc in config.TEAMS_EXCLUDED_TEAMS):
        return False

    if config.TEAMS_MONITORED_TEAMS:
        return any(mon.lower() in name_lower for mon in config.TEAMS_MONITORED_TEAMS)

    return team.get("teamType") == 2


def _is_monitored_channel(team_name: str, ch: Dict[str, Any]) -> bool:
    if ch.get("isGeneral"):
        return True
    team_lower = team_name.lower()
    ch_name = (ch.get("displayName") or "").lower()
    for kw in config.TEAMS_CHANNEL_KEYWORDS:
        if ":" in kw:
            t_kw, c_kw = kw.split(":", 1)
            if t_kw.strip().lower() in team_lower and c_kw.strip().lower() in ch_name:
                return True
        elif kw.lower() in ch_name:
            return True
    return False


def _is_lecturer_or_announcement(msg: Dict[str, Any]) -> bool:
    props = msg.get("properties") or {}
    if (props.get("subject") or "").strip():
        return True
    if props.get("cards"):
        return True
    if str(props.get("importance", "")).lower() == "high":
        return True

    sender = (msg.get("imdisplayname") or "").strip().upper()
    if not sender:
        return False

    if any(lec.upper() in sender for lec in config.TEAMS_LECTURERS):
        return True
    if any(sender.startswith(prefix) or f" {prefix}" in sender for prefix in ACADEMIC_PREFIXES):
        return True

    return False


def _clean_html_content(raw_html: str) -> str:
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    text = soup.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def scrape_teams_messages(page: Page) -> List[Dict[str, Any]]:
    """
    Navigates to Microsoft Teams Web using the existing authenticated browser context,
    captures the chatsvc bearer token & teams list, and fetches recent announcements /
    lecturer messages from monitored course channels.
    """
    if not config.TEAMS_ENABLED:
        return []

    logger.info("Checking Microsoft Teams for new course announcements & lecturer messages...")
    teams_data: Dict[str, Any] = {}
    auth_headers: Dict[str, str] = {}

    def on_response(res) -> None:
        if "api/v3/teams/users/me" in res.url and res.status == 200:
            try:
                teams_data["data"] = res.json()
            except Exception:
                pass

    def on_request(req) -> None:
        if "chatsvc/apac/v1/" in req.url and "authorization" in req.headers:
            auth_headers["authorization"] = req.headers["authorization"]
            if "x-ms-client-version" in req.headers:
                auth_headers["x-ms-client-version"] = req.headers["x-ms-client-version"]

    page.on("response", on_response)
    page.on("request", on_request)

    try:
        page.goto(TEAMS_URL, wait_until="domcontentloaded", timeout=30000)
        for _ in range(25):
            if "login.microsoftonline.com" in page.url:
                logger.warning("Microsoft Teams redirected to login page; skipping Teams check.")
                return []
            if "data" in teams_data and "authorization" in auth_headers:
                break
            page.wait_for_timeout(1000)
    except Exception as e:
        logger.warning(f"Failed to load Microsoft Teams: {e}")
        return []
    finally:
        try:
            page.remove_listener("response", on_response)
            page.remove_listener("request", on_request)
        except Exception:
            pass

    if "data" not in teams_data or "authorization" not in auth_headers:
        logger.warning("Microsoft Teams data or auth token unavailable; skipping Teams check.")
        return []

    teams = teams_data["data"].get("teams", [])
    monitored_teams = [t for t in teams if _is_monitored_team(t)]
    logger.info(f"Teams scan: {len(monitored_teams)} monitored course teams matched out of {len(teams)} total.")

    collected: List[Dict[str, Any]] = []
    for team in monitored_teams:
        team_name = (team.get("displayName") or "").strip()
        channels = [ch for ch in team.get("channels", []) if _is_monitored_channel(team_name, ch)]
        for ch in channels:
            ch_id = ch.get("id", "")
            ch_name = (ch.get("displayName") or "General").strip()
            if not ch_id:
                continue

            enc_id = urllib.parse.quote(ch_id, safe="")
            msg_url = (
                f"https://teams.cloud.microsoft/api/chatsvc/apac/v1/users/ME/"
                f"conversations/{enc_id}/messages?view=msnp24Equivalent&pageSize=15"
            )
            try:
                res = page.evaluate(
                    """async ({url, headers}) => {
                        const r = await fetch(url, {headers});
                        if (!r.ok) return {status: r.status, messages: []};
                        const data = await r.json();
                        return {status: r.status, messages: data.messages || []};
                    }""",
                    {"url": msg_url, "headers": auth_headers},
                )
            except Exception as e:
                logger.warning(f"Error fetching Teams messages for '{team_name} / {ch_name}': {e}")
                continue

            for m in res.get("messages", []):
                mtype = m.get("messagetype") or ""
                if not mtype or mtype.startswith("Event/") or mtype.startswith("ThreadActivity/") or "CallRecording" in mtype:
                    continue

                if not _is_lecturer_or_announcement(m):
                    continue

                props = m.get("properties") or {}
                subject = (props.get("subject") or "").strip()
                clean_text = _clean_html_content(m.get("content") or "")
                if not subject and not clean_text:
                    continue

                msg_id = str(m.get("id") or "")
                if not msg_id:
                    continue

                sender = (m.get("imdisplayname") or "Lecturer").strip()
                deep_link = f"https://teams.cloud.microsoft/l/message/{enc_id}/{msg_id}"

                collected.append({
                    "id": f"teams_{ch_id}_{msg_id}",
                    "team_name": team_name,
                    "channel_name": ch_name,
                    "sender": sender,
                    "subject": subject,
                    "content_snippet": clean_text[:600],
                    "url": deep_link,
                })

    return collected
