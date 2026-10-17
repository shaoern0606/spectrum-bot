import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import unquote
import requests
from bs4 import BeautifulSoup
import config

logger = logging.getLogger(__name__)

def get_authenticated_session() -> Optional[requests.Session]:
    """Creates a requests.Session populated with cookies from auth_state.json."""
    if not config.AUTH_STATE_FILE.exists():
        logger.error(f"Cannot create authenticated session: {config.AUTH_STATE_FILE} not found.")
        return None

    try:
        with open(config.AUTH_STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)

        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })

        for cookie in state.get("cookies", []):
            session.cookies.set(
                cookie["name"],
                cookie["value"],
                domain=cookie.get("domain", "spectrum.um.edu.my")
            )
        return session
    except Exception as e:
        logger.error(f"Error loading cookies for session: {e}")
        return None

def extract_filename_from_headers(headers: dict, fallback_name: str) -> str:
    """Extracts filename from Content-Disposition header or fallback."""
    cd = headers.get("Content-Disposition", "")
    if cd:
        # Match filename*="UTF-8''..." or filename="..." or filename=...
        fn_match = re.search(r"filename\*=UTF-8''([^;]+)", cd, re.IGNORECASE)
        if fn_match:
            return unquote(fn_match.group(1))
        fn_match = re.search(r'filename="([^"]+)"', cd, re.IGNORECASE)
        if fn_match:
            return fn_match.group(1)
        fn_match = re.search(r'filename=([^; ]+)', cd, re.IGNORECASE)
        if fn_match:
            return fn_match.group(1)

    # Sanitize fallback name
    clean = re.sub(r'[\\/*?:"<>|]', "_", fallback_name).strip()
    return clean or "document"

def download_moodle_resource(
    resource_url: str, 
    fallback_title: str = "document", 
    max_mb: int = 48
) -> Tuple[Optional[Path], Optional[str], Optional[str]]:
    """
    Downloads a SPeCTRUM resource file.
    Returns: (Path to temp file, filename, error_message)
    """
    session = get_authenticated_session()
    if not session:
        return None, None, "Authentication session not available. Please run `python main.py --login`."

    try:
        # If it's a folder, check for download_folder.php
        if "/mod/folder/view.php" in resource_url:
            folder_id_match = re.search(r"id=(\d+)", resource_url)
            if folder_id_match:
                resource_url = f"{config.SPECTRUM_BASE_URL}/mod/folder/download_folder.php?id={folder_id_match.group(1)}"

        logger.info(f"Downloading resource from: {resource_url}")
        resp = session.get(resource_url, allow_redirects=True, stream=True, timeout=30)
        
        if resp.status_code != 200:
            return None, None, f"SPeCTRUM returned HTTP {resp.status_code}"

        content_type = resp.headers.get("Content-Type", "").lower()

        # If Moodle returned an HTML page instead of direct file, check for embedded pluginfile
        if "text/html" in content_type:
            soup = BeautifulSoup(resp.text, "html.parser")
            embed_url = None
            for elem in soup.find_all(["object", "iframe", "a"]):
                href = elem.get("data") or elem.get("src") or elem.get("href")
                if href and "pluginfile.php" in href:
                    embed_url = href
                    break
            
            if embed_url:
                logger.info(f"Found embedded pluginfile link: {embed_url}")
                resp = session.get(embed_url, allow_redirects=True, stream=True, timeout=30)
                if resp.status_code != 200:
                    return None, None, f"Failed to download embedded file (HTTP {resp.status_code})"
            else:
                return None, None, "This resource is an interactive page or link, not a downloadable file."

        filename = extract_filename_from_headers(resp.headers, fallback_title)
        
        # Ensure extension if missing
        if "." not in filename:
            if "pdf" in content_type:
                filename += ".pdf"
            elif "zip" in content_type:
                filename += ".zip"
            elif "word" in content_type:
                filename += ".docx"
            elif "powerpoint" in content_type:
                filename += ".pptx"

        # Check Content-Length if available
        cl = resp.headers.get("Content-Length")
        if cl and int(cl) > max_mb * 1024 * 1024:
            size_mb = int(cl) / (1024 * 1024)
            return None, None, f"TOO_LARGE:{size_mb:.1f} MB (Max allowed: {max_mb} MB)"

        # Save to temp file
        temp_dir = Path(tempfile.gettempdir()) / "spectrumbot_downloads"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_file = temp_dir / filename

        downloaded_bytes = 0
        with open(temp_file, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    downloaded_bytes += len(chunk)
                    if downloaded_bytes > max_mb * 1024 * 1024:
                        temp_file.unlink(missing_ok=True)
                        return None, None, f"TOO_LARGE:> {max_mb} MB"

        logger.info(f"Successfully downloaded '{filename}' ({downloaded_bytes} bytes)")
        return temp_file, filename, None

    except Exception as e:
        logger.exception(f"Exception during file download: {e}")
        return None, None, str(e)
