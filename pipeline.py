#!/usr/bin/env python3
"""
UK Parliamentary Corpus Pipeline
================================
Extract structured UK parliamentary debate data from TheyWorkForYou's
scrapedxml XML files and produce yearly CSV corpora.

Usage:
    # Full pipeline for Commons 2010-2020
    python pipeline.py --years 2010-2020 --chambers commons --steps all --members-file ./members/people.json

    # Download only
    python pipeline.py --years 2010 --chambers commons,lords --steps download

    # Parse and enrich (after download)
    python pipeline.py --years 2010 --chambers commons --steps parse,enrich,export --members-file ./members/people.json
"""

import argparse
import json
import logging
import os
import sys
from typing import Dict, List, Optional, Set

from parse import SpeechBlock

logger = logging.getLogger("pipeline")


def main():
    args = _parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Parse inputs
    years = _parse_years(args.years)
    logger.info(f"Years: {years}")

    if args.chambers == "all":
        chambers = ["commons", "lords", "westminster", "standing"]
    else:
        chambers = [c.strip() for c in args.chambers.split(",")]
    logger.info(f"Chambers: {chambers}")

    if args.steps == "all":
        steps = {"download", "parse", "enrich", "export"}
    else:
        steps = {s.strip() for s in args.steps.split(",")}
    logger.info(f"Steps: {steps}")

    # Validate steps
    valid_steps = {"download", "parse", "enrich", "export", "all"}
    unknown = steps - valid_steps
    if unknown:
        logger.error(f"Unknown steps: {unknown}")
        sys.exit(1)

    # Validate members file if enrich step is requested
    if "enrich" in steps:
        if not os.path.exists(args.members_file):
            logger.error(f"Member file not found: {args.members_file}")
            logger.error(
                "Download people.json from:\n"
                "  curl -L -o members/people.json "
                "https://github.com/mysociety/parlparse/raw/master/members/people.json"
            )
            logger.error(
                "Or clone the full repo:\n"
                "  git clone https://github.com/mysociety/parlparse.git /tmp/parlparse\n"
                "  cp /tmp/parlparse/members/people.json ./members/"
            )
            sys.exit(1)

    # Ensure directories exist
    os.makedirs(args.data_dir, exist_ok=True)
    os.makedirs(args.output_dir, exist_ok=True)
    os.makedirs(os.path.dirname(args.members_file) or ".", exist_ok=True)

    # --- Run pipeline steps ---
    speeches: Optional[List[SpeechBlock]] = None

    # Step 1: Download
    if "download" in steps:
        logger.info("=" * 60)
        logger.info("STEP 1/4: Downloading debate XML files")
        logger.info("=" * 60)
        from download import download_files, download_standing_files

        # Separate standing from other chambers (different download strategy)
        standard_chambers = [c for c in chambers if c != "standing"]
        if standard_chambers:
            download_files(years, standard_chambers, args.data_dir, args.max_workers)
        if "standing" in chambers:
            download_standing_files(years, args.data_dir, args.max_workers)

    # Step 2: Parse
    if "parse" in steps:
        logger.info("=" * 60)
        logger.info("STEP 2/4: Parsing XML files into speech blocks")
        logger.info("=" * 60)
        from parse import parse_files

        speeches = parse_files(args.data_dir)

        # Save interim JSON for restartability
        interim_path = os.path.join(args.output_dir, "speeches_interim.json")
        logger.info(f"Saving interim data to {interim_path}")
        with open(interim_path, "w", encoding="utf-8") as f:
            json.dump(
                [_speech_to_dict(s) for s in speeches],
                f,
                ensure_ascii=False,
            )

    # Step 3: Enrich with party data
    if "enrich" in steps:
        logger.info("=" * 60)
        logger.info("STEP 3/4: Enriching with party affiliations")
        logger.info("=" * 60)
        from enrich import enrich_speeches, load_member_data

        if speeches is None:
            speeches = _load_interim(args.output_dir)

        member_lookup, name_lookup = load_member_data(args.members_file)
        speeches = enrich_speeches(speeches, member_lookup, name_lookup)

        # Save enriched interim
        enriched_path = os.path.join(args.output_dir, "speeches_enriched.json")
        logger.info(f"Saving enriched data to {enriched_path}")
        with open(enriched_path, "w", encoding="utf-8") as f:
            json.dump(
                [_speech_to_dict(s) for s in speeches],
                f,
                ensure_ascii=False,
            )

    # Step 4: Export to CSV
    if "export" in steps:
        logger.info("=" * 60)
        logger.info("STEP 4/4: Exporting to yearly CSV files")
        logger.info("=" * 60)
        from export import export_to_csv

        if speeches is None:
            speeches = _load_interim(args.output_dir)

        written = export_to_csv(speeches, args.output_dir, annual_files=True)

        logger.info(f"\nExported {len(written)} CSV files to {args.output_dir}/")
        for path in written:
            size_mb = os.path.getsize(path) / (1024 * 1024)
            logger.info(f"  {os.path.basename(path)} ({size_mb:.1f} MB)")

    logger.info("=" * 60)
    logger.info("Pipeline complete!")
    logger.info("=" * 60)


def _parse_args():
    parser = argparse.ArgumentParser(
        description="UK Parliamentary Corpus Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full pipeline: download + parse + enrich + export
  python pipeline.py --years 2010-2020 --chambers all --steps all \\
      --members-file ./members/people.json

  # Just download Commons and Lords debates for 2010
  python pipeline.py --years 2010 --chambers commons,lords --steps download

  # Parse and export already-downloaded data
  python pipeline.py --years 2010 --chambers commons --steps parse,export
        """,
    )

    parser.add_argument(
        "--years",
        type=str,
        required=True,
        help='Years to process: "2010-2020" or "2010,2011,2012"',
    )
    parser.add_argument(
        "--chambers",
        type=str,
        default="all",
        help='Chambers: "commons,lords,westminster,standing" or "all" (default: all)',
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="./data",
        help="Directory for downloaded XML files (default: ./data)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./output",
        help="Directory for CSV output (default: ./output)",
    )
    parser.add_argument(
        "--members-file",
        type=str,
        default="./members/people.json",
        help="Path to people.json member lookup (default: ./members/people.json)",
    )
    parser.add_argument(
        "--steps",
        type=str,
        default="all",
        help="Pipeline steps: download,parse,enrich,export,all (default: all)",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=10,
        help="Max parallel download threads (default: 10)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable debug-level logging",
    )

    return parser.parse_args()


def _parse_years(years_str: str) -> List[int]:
    """Parse year specifications like '2010-2020' or '2010,2011,2012'."""
    years: List[int] = []
    for part in years_str.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            years.extend(range(int(start), int(end) + 1))
        else:
            years.append(int(part))
    return sorted(set(years))


def _speech_to_dict(s: SpeechBlock) -> dict:
    """Convert SpeechBlock to JSON-serializable dict."""
    return {
        "speaker_name": s.speaker_name,
        "speaker_id": s.speaker_id,
        "speaker_party": s.speaker_party,
        "text": s.text,
        "date": s.date,
        "discussion_title": s.discussion_title,
        "chamber": s.chamber,
        "venue": s.venue,
        "colnum": s.colnum,
        "time": s.time,
        "url": s.url,
    }


def _dict_to_speech(d: dict) -> SpeechBlock:
    """Convert dict back to SpeechBlock."""
    return SpeechBlock(
        speaker_name=d["speaker_name"],
        speaker_id=d["speaker_id"],
        speaker_party=d.get("speaker_party", ""),
        text=d["text"],
        date=d["date"],
        discussion_title=d["discussion_title"],
        chamber=d["chamber"],
        venue=d.get("venue", ""),
        colnum=d.get("colnum", ""),
        time=d.get("time", ""),
        url=d.get("url", ""),
    )


def _load_interim(output_dir: str) -> List[SpeechBlock]:
    """Load speeches from the interim JSON file."""
    # Try enriched first, then basic interim
    for filename in ["speeches_enriched.json", "speeches_interim.json"]:
        path = os.path.join(output_dir, filename)
        if os.path.exists(path):
            logger.info(f"Loading interim data from {path}")
            with open(path, "r", encoding="utf-8") as f:
                return [_dict_to_speech(d) for d in json.load(f)]

    logger.error(
        "No interim data found in %s. Run the parse step first.", output_dir
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
