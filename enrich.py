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


def _build_full_name(name_parts) -> str:
    """Build a canonical full name from a Popolo name object.

    For Lords/peers, builds the titled form used in Hansard XML
    (e.g. "Baroness Smith of Basildon", "Lord True").
    For MPs, builds "GivenName FamilyName" form.
    """
    if not isinstance(name_parts, dict):
        return str(name_parts).strip() if name_parts else ""
    given = name_parts.get("given_name", "")
    family = name_parts.get("family_name", "")
    lordname = name_parts.get("lordname", "")
    honorific = name_parts.get("honorific_prefix", "")
    lordof = name_parts.get("lordofname", "")

    if lordname:
        # Build peerage name: "Baroness Smith of Basildon" or "Lord True"
        base = f"{honorific} {lordname}".strip()
        if lordof:
            base = f"{base} of {lordof}"
        return base
    return f"{given} {family}".strip()


def _make_membership_record(m: dict) -> dict:
    """Convert a raw Popolo membership dict into our standard record format."""
    party_slug = m.get("on_behalf_of_id", "")
    return {
        "name": _build_full_name(m.get("name", {})),
        "party": _normalize_party(party_slug),
        "party_slug": party_slug,
        "organization_id": m.get("organization_id", ""),
        "start_date": m.get("start_date", ""),
        "end_date": m.get("end_date", ""),
    }


def load_member_data(members_path: str) -> tuple:
    """Load people.json and build both ID-based and name-based lookups.

    Returns a tuple of (member_lookup, name_lookup) where:
      - member_lookup: member_id -> [membership dicts] (existing behavior)
      - name_lookup: speaker_name -> [membership dicts] (fallback for when
        speakerid is missing from the XML, as seen in 2025+ data)
    """
    logger.info(f"Loading member data from {members_path}")

    with open(members_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # --- ID-based lookup (original behavior) ---
    lookup: Dict[str, List[dict]] = {}
    memberships = data.get("memberships", [])

    for m in memberships:
        member_id = m.get("id", "")
        if not member_id:
            continue
        if member_id not in lookup:
            lookup[member_id] = []
        lookup[member_id].append(_make_membership_record(m))

    # Log stats
    total_memberships = sum(len(v) for v in lookup.values())
    members_with_multiple = sum(1 for v in lookup.values() if len(v) > 1)
    logger.info(
        f"ID lookup: {total_memberships:,} records for {len(lookup):,} member IDs "
        f"({members_with_multiple} with multiple memberships)"
    )

    # --- Name-based lookup (fallback for missing speakerid) ---
    # Build person_id -> name mapping from persons array (including alt names)
    pid_to_names: Dict[str, List[str]] = defaultdict(list)
    for p in data.get("persons", []):
        pid = p.get("id", "")
        if not pid:
            continue
        canonical = _build_full_name(p.get("name", {}))
        if canonical:
            pid_to_names[pid].append(canonical)
        for alt in p.get("other_names", []):
            alt_name = _build_full_name(alt)
            if alt_name and alt_name != canonical:
                pid_to_names[pid].append(alt_name)

    # Build person_id -> memberships
    pid_to_memberships: Dict[str, List[dict]] = defaultdict(list)
    for m in memberships:
        pid = m.get("person_id", "")
        if pid:
            pid_to_memberships[pid].append(_make_membership_record(m))

    # Build name -> memberships
    name_lookup: Dict[str, List[dict]] = defaultdict(list)
    for pid, names in pid_to_names.items():
        if pid not in pid_to_memberships:
            continue
        records = pid_to_memberships[pid]
        for name in names:
            for r in records:
                name_lookup[name].append(r)

    unique_names = len(name_lookup)
    logger.info(
        f"Name lookup: {sum(len(v) for v in name_lookup.values()):,} records "
        f"for {unique_names:,} unique names"
    )

    return lookup, dict(name_lookup)


def enrich_speeches(
    speeches: List[SpeechBlock],
    member_lookup: Dict[str, List[dict]],
    name_lookup: Optional[Dict[str, List[dict]]] = None,
) -> List[SpeechBlock]:
    """Add party affiliation to each speech block.

    Tries speaker_id match first, then falls back to name-based matching
    for speeches where speaker_id is missing (common in 2025+ XML).

    Args:
        speeches: List of SpeechBlock objects from the parse step.
        member_lookup: ID-based lookup from load_member_data().
        name_lookup: Optional name-based fallback lookup from load_member_data().

    Returns:
        The same list of SpeechBlock objects with speaker_party populated.
    """
    enriched: List[SpeechBlock] = []
    missing_ids: Dict[str, int] = defaultdict(int)
    missing_names: Dict[str, int] = defaultdict(int)
    date_matched: int = 0
    fallback_matched: int = 0
    name_matched: int = 0

    for speech in speeches:
        memberships = member_lookup.get(speech.speaker_id)

        # Fall back to name lookup if speaker_id is empty/missing
        if not memberships and name_lookup and not speech.speaker_id:
            memberships = name_lookup.get(speech.speaker_name)
            if memberships:
                name_matched += 1

        if memberships:
            best = _find_membership_for_date(memberships, speech.date)
            if best:
                speech.speaker_party = best["party"]
                date_matched += 1
            else:
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
        f"(date-matched: {date_matched:,}, fallback: {fallback_matched:,}, "
        f"name-matched: {name_matched:,})"
    )

    if missing_ids:
        logger.warning(
            f"Missing party for {len(missing_ids)} unique speaker IDs "
            f"({sum(missing_ids.values())} speech blocks)"
        )
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
