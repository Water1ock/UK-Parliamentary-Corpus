"""
Download UK parliamentary debate XML files from TheyWorkForYou.

Downloads files over HTTP from data.theyworkforyou.com for specified years
and chambers. Scans variants from 'i' down to 'a' (newest first) since recent
years split debates across multiple variants (a through f in 2024, c in 2025).
Uses concurrent downloads for speed.
"""

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from typing import List, Optional, Set

import requests
from tqdm import tqdm

logger = logging.getLogger(__name__)

# URL templates and server directory names for each chamber.
# {date} is formatted as YYYY-MM-DD.
CHAMBER_URLS = {
    "commons": "https://www.theyworkforyou.com/pwdata/scrapedxml/debates/debates{date}a.xml",
    "lords": "https://www.theyworkforyou.com/pwdata/scrapedxml/lordspages/daylord{date}a.xml",
    "westminster": "https://www.theyworkforyou.com/pwdata/scrapedxml/westminhall/westminster{date}a.xml",
}

# Map user-facing chamber keys to the actual server directory names.
# These must match parse.py's CHAMBER_MAP keys.
CHAMBER_DIR_MAP = {
    "commons": "debates",
    "lords": "lordspages",
    "westminster": "westminhall",
}

# Debate files can have multiple variants (a through f in 2024, c in 2025).
# Recent years split debates across many files due to redirect chains.
# We try the latest variant first (most complete) and fall back to earlier ones.
# Order: i -> h -> g -> f -> e -> d -> c -> b -> a
# Covers up to 2026+ by including i, h, g proactively.
VARIANT_ORDER = ["i", "h", "g", "f", "e", "d", "c", "b", "a"]


def download_files(
    years: List[int],
    chambers: List[str],
    data_dir: str = "./data",
    max_workers: int = 10,
) -> List[str]:
    """Download debate XML files for the given years and chambers.

    Args:
        years: List of years to download, e.g. [2010, 2011, 2012].
        chambers: List of chamber keys: 'commons', 'lords', 'westminster'.
        data_dir: Root directory to store downloaded files.
        max_workers: Number of concurrent download threads.

    Returns:
        List of file paths that were downloaded or already existed.
    """
    os.makedirs(data_dir, exist_ok=True)

    # Build list of (chamber, date_str, chamber_dir) tasks
    tasks: List[tuple] = []
    for year in years:
        for chamber in chambers:
            if chamber not in CHAMBER_URLS:
                logger.warning(f"Unknown chamber: {chamber}, skipping")
                continue

            # Use the server-side directory name so parse.py can find the files
            server_dir = CHAMBER_DIR_MAP.get(chamber, chamber)
            chamber_dir = os.path.join(data_dir, server_dir)
            os.makedirs(chamber_dir, exist_ok=True)

            for d in _weekdays_in_year(year):
                date_str = d.strftime("%Y-%m-%d")
                tasks.append((chamber, date_str, chamber_dir))

    logger.info(
        f"Attempting to download from {len(tasks)} dates "
        f"across {len(chambers)} chamber(s), {len(years)} year(s)"
    )

    downloaded: List[str] = []
    already_had: int = 0
    not_found: int = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_download_one, task): task for task in tasks}

        with tqdm(total=len(tasks), desc="Downloading", unit="file") as pbar:
            for future in as_completed(futures):
                result, skipped = future.result()
                if result:
                    downloaded.append(result)
                if skipped:
                    already_had += 1
                else:
                    not_found += 1 if not result else 0
                pbar.update(1)

    logger.info(
        f"Download complete: {len(downloaded)} downloaded, "
        f"{already_had} already cached, {not_found} not found on server"
    )
    return downloaded


def _download_one(task: tuple) -> tuple:
    """Download a single file. Returns (filepath | None, was_skipped: bool).

    Tries variants in reverse order (i through a) since the latest
    variant is the most complete. For older data only a/b exist, so
    later variants will 404 quickly.
    """
    chamber, date_str, chamber_dir = task

    url_template = CHAMBER_URLS[chamber]

    # Check if any variant already exists on disk
    for variant in VARIANT_ORDER:
        url = url_template.format(date=date_str).replace("a.xml", f"{variant}.xml")
        filepath = os.path.join(chamber_dir, os.path.basename(url))
        if os.path.exists(filepath):
            return (filepath, True)

    # No cached variant found — download the newest available
    for variant in VARIANT_ORDER:
        url = url_template.format(date=date_str).replace("a.xml", f"{variant}.xml")
        filename = os.path.basename(url)
        filepath = os.path.join(chamber_dir, filename)

        try:
            resp = requests.get(url, timeout=30, headers={
                "User-Agent": "UK-Parliamentary-Corpus/1.0 (academic research)"
            })
            if resp.status_code == 200:
                with open(filepath, "wb") as f:
                    f.write(resp.content)
                return (filepath, False)
            elif resp.status_code == 404:
                continue
            else:
                logger.debug(f"HTTP {resp.status_code} for {url}")
        except requests.RequestException as e:
            logger.debug(f"Request failed for {url}: {e}")
            continue

    return (None, False)


def _weekdays_in_year(year: int):
    """Generate all Monday-Friday dates in a given year."""
    d = date(year, 1, 1)
    end = date(year, 12, 31)
    while d <= end:
        if d.weekday() < 5:  # Monday = 0, Friday = 4
            yield d
        d += timedelta(days=1)
