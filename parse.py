"""
Parse TheyWorkForYou scrapedxml debate files into structured SpeechBlock objects.

Handles ISO-8859-1 encoding, DTD entities, nested HTML within speech paragraphs,
heading-based topic tracking, and filtering of procedural/non-speech elements.
"""

import logging
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

from lxml import etree
from tqdm import tqdm

logger = logging.getLogger(__name__)


@dataclass
class SpeechBlock:
    """A single parliamentary utterance with all metadata."""

    speaker_name: str
    speaker_id: str
    speaker_party: str = ""
    text: str = ""
    date: str = ""
    discussion_title: str = ""
    chamber: str = ""
    venue: str = ""
    colnum: str = ""
    time: str = ""
    url: str = ""


# Map directory names to (chamber, venue) tuples.
# Chamber = constitutional body (Commons/Lords).
# Venue = physical sitting location (Main Chamber, Westminster Hall, Lords Chamber).
CHAMBER_MAP = {
    "debates": ("Commons", "Main Chamber"),
    "lordspages": ("Lords", "Lords Chamber"),
    "westminhall": ("Commons", "Westminster Hall"),
}


def parse_files(data_dir: str) -> List[SpeechBlock]:
    """Parse all downloaded XML files and extract speech blocks.

    Args:
        data_dir: Path to the directory containing chamber subdirectories
                  (e.g. ./data/ containing debates/, lordspages/, westminhall/).

    Returns:
        List of SpeechBlock objects extracted from all XML files.
    """
    speeches: List[SpeechBlock] = []

    for chamber_dir_name, (chamber_label, venue_label) in CHAMBER_MAP.items():
        chamber_path = os.path.join(data_dir, chamber_dir_name)
        if not os.path.isdir(chamber_path):
            logger.debug(f"Chamber directory not found: {chamber_path}")
            continue

        xml_files = sorted(
            f for f in os.listdir(chamber_path) if f.endswith(".xml")
        )
        logger.info(f"Found {len(xml_files)} XML files in {chamber_label} ({venue_label})")

        for filename in tqdm(xml_files, desc=f"Parsing {chamber_label}", unit="file"):
            filepath = os.path.join(chamber_path, filename)
            try:
                file_speeches = _parse_file(filepath, chamber_label, venue_label)
                speeches.extend(file_speeches)
            except Exception as e:
                logger.error(f"Error parsing {filename}: {e}")

    logger.info(f"Total speech blocks parsed: {len(speeches):,}")
    return speeches


def _parse_file(filepath: str, chamber: str, venue: str) -> List[SpeechBlock]:
    """Parse a single XML debate file.

    Tracks <major-heading> and <minor-heading> elements to build the
    discussion_title for each speech.
    """
    date_str = _extract_date_from_filename(os.path.basename(filepath))

    # Use a permissive parser: recover from errors, handle ISO-8859-1,
    # and resolve HTML/DTD entities (&ndash;, &pound;, etc.)
    parser = etree.XMLParser(
        recover=True, encoding="ISO-8859-1", resolve_entities=True
    )
    try:
        tree = etree.parse(filepath, parser)
    except etree.XMLSyntaxError as e:
        logger.warning(f"XML syntax error in {os.path.basename(filepath)}: {e}")
        return []

    root = tree.getroot()
    speeches: List[SpeechBlock] = []

    # Track current heading context
    current_major: str = ""
    current_minor: str = ""

    for elem in root:
        tag = elem.tag
        # Strip namespace if present
        if "}" in tag:
            tag = tag.split("}", 1)[1]

        if tag == "major-heading":
            current_major = _get_text_content(elem).strip()
            current_minor = ""
        elif tag == "minor-heading":
            current_minor = _get_text_content(elem).strip()
        elif tag == "speech":
            speech = _parse_speech(
                elem, date_str, chamber, venue, current_major, current_minor
            )
            if speech:
                speeches.append(speech)
        # Ignore gidredirect, oral-q, and other non-speech elements

    return speeches


def _parse_speech(
    elem,
    date_str: str,
    chamber: str,
    venue: str,
    major_title: str,
    minor_title: str,
) -> Optional[SpeechBlock]:
    """Parse a single <speech> element into a SpeechBlock.

    Returns None for procedural items (nospeaker=true) or empty speeches.
    """
    # Skip procedural / non-speech items (e.g. "The following Members took the Oath")
    if elem.get("nospeaker") == "true":
        return None

    speaker_name = (elem.get("speakername") or "").strip()
    speaker_id = (elem.get("speakerid") or "").strip()

    if not speaker_name or not speaker_id:
        return None

    # Extract all text from child <p> elements, preserving nested tag content
    text_parts: List[str] = []
    for p in elem.findall("p"):
        part = _get_text_content(p).strip()
        if part:
            text_parts.append(part)

    # Join paragraphs preserving structure: single newline between paragraphs
    # within a speech, no trailing newline
    text = "\n".join(text_parts).strip()
    if not text:
        return None

    # Build full discussion title
    discussion_title = major_title
    if minor_title:
        if discussion_title:
            discussion_title += " — " + minor_title
        else:
            discussion_title = minor_title

    return SpeechBlock(
        speaker_name=speaker_name,
        speaker_id=speaker_id,
        speaker_party="",  # Filled in during enrichment step
        text=text,
        date=date_str,
        discussion_title=discussion_title,
        chamber=chamber,
        venue=venue,
        colnum=elem.get("colnum", ""),
        time=elem.get("time", ""),
        url=elem.get("url", ""),
    )


def _get_text_content(elem) -> str:
    """Extract all text from an lxml element, stripping tags but preserving content.

    This handles nested HTML like <i>, <phrase>, and resolves entities like
    &ndash;, &pound;, &#8211; correctly via the DTD declarations.

    Using tostring(method="text") is more reliable than .text or .text_content()
    because it recursively concatenates text and tail of all descendants.
    """
    return (etree.tostring(elem, method="text", encoding="unicode") or "")


def _extract_date_from_filename(filename: str) -> str:
    """Extract YYYY-MM-DD from filenames like 'debates2010-05-25a.xml'
    or 'daylord1999-11-17a.xml'."""
    match = re.search(r"(\d{4}-\d{2}-\d{2})", filename)
    if match:
        return match.group(1)
    logger.warning(f"Could not extract date from filename: {filename}")
    return ""
