"""
Export enriched speech blocks to yearly CSV files.

Output files are named Hansard_YYYY.csv containing all debate speeches
from that calendar year with columns:
  speaker_name, speaker_party, text, date, discussion_title, chamber, venue
"""

import csv
import logging
import os
from collections import defaultdict
from typing import List

from parse import SpeechBlock

logger = logging.getLogger(__name__)

CSV_HEADERS = [
    "speaker_name",
    "speaker_party",
    "text",
    "date",
    "discussion_title",
    "chamber",
    "venue",
]


def export_to_csv(
    speeches: List[SpeechBlock],
    output_dir: str = "./output",
    annual_files: bool = True,
) -> List[str]:
    """Export speeches to CSV files.

    Args:
        speeches: Enriched speech blocks.
        output_dir: Directory to write CSV files.
        annual_files: If True, split into one file per year (Hansard_YYYY.csv).
                      If False, write a single file.

    Returns:
        List of file paths written.
    """
    os.makedirs(output_dir, exist_ok=True)
    written: List[str] = []

    if annual_files:
        # Group speeches by year (extracted from date field)
        by_year: dict = defaultdict(list)
        for speech in speeches:
            year = speech.date[:4] if speech.date else "unknown"
            by_year[year].append(speech)

        for year in sorted(by_year.keys()):
            year_speeches = sorted(by_year[year], key=lambda s: s.date)
            filepath = os.path.join(output_dir, f"Hansard_{year}.csv")
            _write_csv(filepath, year_speeches)
            written.append(filepath)

        # Summary
        total = sum(len(v) for v in by_year.values())
        logger.info(
            f"Exported {total:,} speeches across {len(by_year)} yearly CSV files"
        )

        # Print per-year counts
        for year in sorted(by_year.keys()):
            logger.info(f"  {year}: {len(by_year[year]):,} speeches")
    else:
        filepath = os.path.join(output_dir, "Hansard_all.csv")
        _write_csv(filepath, speeches)
        written.append(filepath)
        logger.info(f"Exported {len(speeches):,} speeches to {filepath}")

    return written


def _write_csv(filepath: str, speeches: List[SpeechBlock]) -> None:
    """Write a list of speeches to a CSV file with proper quoting."""
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=CSV_HEADERS,
            quoting=csv.QUOTE_ALL,
        )
        writer.writeheader()

        for speech in speeches:
            writer.writerow({
                "speaker_name": speech.speaker_name,
                "speaker_party": speech.speaker_party,
                "text": speech.text,
                "date": speech.date,
                "discussion_title": speech.discussion_title,
                "chamber": speech.chamber,
                "venue": speech.venue,
            })

    logger.debug(f"Wrote {len(speeches):,} rows to {os.path.basename(filepath)}")
