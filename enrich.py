"""
Enrich speech blocks with speaker party affiliation.

Loads people.json (Popolo format) from the ParlParse project and builds
a lookup from member ID to party and name information. Matches the
speakerid attribute in debate XML (e.g. 'uk.org.publicwhip/member/40400')
to the 'id' field of membership objects in people.json.
"""

import json
import logging
from collections import defaultdict
from typing import Dict, List, Optional

from parse import SpeechBlock

logger = logging.getLogger(__name__)


# Normalize party slugs to human-readable names
PARTY_NAME_MAP = {
    "labour": "Labour",
    "labour-cooperative": "Labour (Co-op)",
    "conservative": "Conservative",
    "liberal-democrat": "Liberal Democrat",
    "liberal_democrat": "Liberal Democrat",
    "scottish-national-party": "Scottish National Party",
    "green-party": "Green Party",
    "dup": "Democratic Unionist Party",
    "sinn-fein": "Sinn Féin",
    "plaid-cymru": "Plaid Cymru",
    "sdlp": "SDLP",
    "alliance": "Alliance Party",
    "uk-independence-party": "UK Independence Party",
    "independent": "Independent",
    "speaker": "Speaker",
    "crossbench": "Crossbench",
    "non-affiliated": "Non-affiliated",
    "bishop": "Bishops",
    "conservative-independent": "Conservative Independent",
    "labour-independent": "Labour Independent",
    "change-uk": "Change UK",
    "the-independent-group": "The Independent Group",
    "reform-uk": "Reform UK",
    "alba": "Alba",
}


def _normalize_party(slug: str) -> str:
    """Convert a party slug like 'labour' to a display name like 'Labour'."""
    if not slug:
        return "Unknown"
    slug_lower = slug.lower().strip()
    if slug_lower in PARTY_NAME_MAP:
        return PARTY_NAME_MAP[slug_lower]
    # Fallback: capitalize each word for unknown parties
    return slug.replace("-", " ").title()


def load_member_data(members_path: str) -> Dict[str, List[dict]]:
    """Load people.json in Popolo format and build a member-ID lookup.

    The Popolo memberships array contains objects with:
      - id: "uk.org.publicwhip/member/1656"  (matches speakerid in XML)
      - on_behalf_of_id: "labour"             (party slug)
      - name: {given_name, family_name, ...}
      - organization_id: "house-of-commons" or "house-of-lords"
      - start_date, end_date

    Each member ID can have MULTIPLE membership records (e.g. when an MP
    changes party or constituency). We store all of them as a list so that
    enrichment can match the correct one based on the speech date.

    Args:
        members_path: Path to people.json from the ParlParse project.

    Returns:
        Dict mapping member ID string -> list of membership dicts.
        Each membership dict has: name, party, organization_id,
        start_date, end_date.
    """
    logger.info(f"Loading member data from {members_path}")

    with open(members_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    lookup: Dict[str, List[dict]] = {}
    memberships = data.get("memberships", [])

    if not memberships:
        logger.warning("No 'memberships' key found in people.json")

    for m in memberships:
        member_id = m.get("id", "")
        if not member_id:
            continue

        party_slug = m.get("on_behalf_of_id", "")
        party_name = _normalize_party(party_slug)

        # Build human-readable name from Popolo name object
        name_parts = m.get("name", {})
        if isinstance(name_parts, dict):
            given = name_parts.get("given_name", "")
            family = name_parts.get("family_name", "")
            # Lords may use lordname instead of family_name
            lordname = name_parts.get("lordname", "")
            honorific = name_parts.get("honorific_prefix", "")

            if lordname:
                display_name = f"{honorific} {given} {lordname}".strip()
            else:
                display_name = f"{given} {family}".strip()
        elif isinstance(name_parts, str):
            display_name = name_parts
        else:
            display_name = ""

        if member_id not in lookup:
            lookup[member_id] = []

        lookup[member_id].append({
            "name": display_name,
            "party": party_name,
            "party_slug": party_slug,
            "organization_id": m.get("organization_id", ""),
            "start_date": m.get("start_date", ""),
            "end_date": m.get("end_date", ""),
        })

    # Log stats
    total_memberships = sum(len(v) for v in lookup.values())
    members_with_multiple = sum(1 for v in lookup.values() if len(v) > 1)
    logger.info(
        f"Loaded {total_memberships:,} membership records "
        f"for {len(lookup):,} unique member IDs "
        f"({members_with_multiple} with multiple memberships)"
    )

    # Report party distribution (from the longest/most recent membership for each ID)
    party_counts = defaultdict(int)
    for v in lookup.values():
        # Use last membership (most recent) for stats
        party_counts[v[-1]["party"]] += 1
    top_parties = sorted(party_counts.items(), key=lambda x: -x[1])[:10]
    logger.info(f"Top parties: {', '.join(f'{p}({c})' for p, c in top_parties)}")

    return lookup


def enrich_speeches(
    speeches: List[SpeechBlock],
    member_lookup: Dict[str, List[dict]],
) -> List[SpeechBlock]:
    """Add party affiliation to each speech block.

    Matches speech.speaker_id against the member_lookup keys.
    When multiple memberships exist for a speaker_id, selects the one
    whose date range covers the speech date (most common case).
    Falls back to the most recent membership if no date match.

    Args:
        speeches: List of SpeechBlock objects from the parse step.
        member_lookup: Dict from load_member_data() mapping IDs to lists
                       of membership dicts.

    Returns:
        The same list of SpeechBlock objects with speaker_party populated.
    """
    enriched: List[SpeechBlock] = []
    missing_ids: Dict[str, int] = defaultdict(int)
    missing_names: Dict[str, int] = defaultdict(int)
    date_matched: int = 0
    fallback_matched: int = 0

    for speech in speeches:
        memberships = member_lookup.get(speech.speaker_id)

        if memberships:
            # Try to match by date range first
            best = _find_membership_for_date(memberships, speech.date)
            if best:
                speech.speaker_party = best["party"]
                date_matched += 1
            else:
                # Fallback: use most recent membership (last in list)
                speech.speaker_party = memberships[-1]["party"]
                fallback_matched += 1
        else:
            speech.speaker_party = "Unknown"
            missing_ids[speech.speaker_id] += 1
            missing_names[speech.speaker_name] += 1

        enriched.append(speech)

    # Report coverage statistics
    total = len(speeches)
    matched = total - sum(missing_ids.values())
    logger.info(
        f"Party coverage: {matched:,}/{total:,} "
        f"({100 * matched / total:.1f}%) matched "
        f"(date-matched: {date_matched:,}, fallback: {fallback_matched:,})"
    )

    if missing_ids:
        logger.warning(
            f"Missing party for {len(missing_ids)} unique speaker IDs "
            f"({sum(missing_ids.values())} speech blocks)"
        )
        # Show top-10 most frequent unmatched speakers
        top_missing = sorted(missing_names.items(), key=lambda x: -x[1])[:10]
        logger.warning(
            "Top unmatched speakers: "
            + ", ".join(f"{name}({count})" for name, count in top_missing)
        )

    return enriched


def _find_membership_for_date(
    memberships: List[dict], speech_date: str
) -> Optional[dict]:
    """Find the membership whose date range covers the speech date.

    Returns the best matching membership, or None if no date-based match is found
    (e.g. when start_date/end_date are missing).
    """
    if not speech_date:
        return None

    candidates = []
    for m in memberships:
        start = m.get("start_date", "")
        end = m.get("end_date", "")
        if not start:
            continue
        # Membership covers the speech date if speech_date >= start
        # and (end is empty/future or speech_date <= end)
        if speech_date >= start and (not end or speech_date <= end):
            candidates.append(m)

    if candidates:
        # If multiple matches (rare), prefer the most specific (earliest end_date)
        candidates.sort(key=lambda m: m.get("end_date", "9999-99-99"))
        return candidates[0]

    return None
