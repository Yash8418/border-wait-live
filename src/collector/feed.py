"""Download and parse CBSA's current border wait times feed.

The feed is a CSV-like file that uses ';;' as its separator, starts with a UTF-8
byte-order mark, and reports times in each crossing's local timezone (e.g. EST, PDT).
"""

from __future__ import annotations

import re
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

FEED_URL = "https://www.cbsa-asfc.gc.ca/bwt-taf/bwt-eng.csv"
USER_AGENT = "border-wait-live/1.0 (+https://github.com/Yash8418/border-wait-live)"

TZ_OFFSETS_HOURS = {
    "NDT": -2.5,
    "NST": -3.5,
    "ADT": -3,
    "AST": -4,
    "EDT": -4,
    "EST": -5,
    "CDT": -5,
    "CST": -6,
    "MDT": -6,
    "MST": -7,
    "PDT": -7,
    "PST": -8,
    "AKDT": -8,
    "AKST": -9,
}

_MINUTES = re.compile(r"^(\d+)\s*(?:min(?:ute)?s?)?$", re.IGNORECASE)
_TIMESTAMP = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\s+([A-Z]{3,4})$")


@dataclass(frozen=True)
class Wait:
    status: str  # reported | not_reported | closed | not_applicable | unknown
    minutes: int | None


@dataclass(frozen=True)
class Reading:
    crossing_id: str
    office: str
    location: str
    observed_at: datetime  # timezone-aware, as published by CBSA
    commercial_canada: Wait
    commercial_us: Wait
    travellers_canada: Wait
    travellers_us: Wait


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def parse_wait(value: str) -> Wait:
    text = value.strip()
    lowered = text.lower()
    if lowered == "no delay":
        return Wait("reported", 0)
    if text in ("--", ""):
        return Wait("not_reported", None)
    if lowered in ("closed", "temporarily closed"):
        return Wait("closed", None)
    if lowered == "not applicable":
        return Wait("not_applicable", None)
    match = _MINUTES.match(text)
    if match:
        return Wait("reported", int(match.group(1)))
    return Wait("unknown", None)


def parse_timestamp(value: str) -> datetime:
    match = _TIMESTAMP.match(value.strip())
    if not match or match.group(2) not in TZ_OFFSETS_HOURS:
        raise ValueError(f"Unrecognised timestamp: {value!r}")
    local, zone = match.groups()
    offset = timezone(timedelta(hours=TZ_OFFSETS_HOURS[zone]))
    return datetime.strptime(local, "%Y-%m-%d %H:%M").replace(tzinfo=offset)


def parse_feed(text: str) -> tuple[list[Reading], list[str]]:
    """Parse the feed. Returns (readings, errors); one bad line never breaks the whole run."""
    lines = [line for line in text.lstrip("﻿").splitlines() if line.strip()]
    readings, errors = [], []
    for number, line in enumerate(lines[1:], start=2):  # line 1 is the header
        cells = [cell.strip() for cell in line.split(";;")]
        if len(cells) < 7:
            errors.append(f"line {number}: expected 7 fields, got {len(cells)}")
            continue
        office, location, updated, com_ca, com_us, trav_ca, trav_us = cells[:7]
        try:
            observed_at = parse_timestamp(updated)
        except ValueError as error:
            errors.append(f"line {number}: {error}")
            continue
        readings.append(
            Reading(
                crossing_id=slugify(office),
                office=office,
                location=location,
                observed_at=observed_at,
                commercial_canada=parse_wait(com_ca),
                commercial_us=parse_wait(com_us),
                travellers_canada=parse_wait(trav_ca),
                travellers_us=parse_wait(trav_us),
            )
        )
    return readings, errors


def download_feed(url: str = FEED_URL, timeout: int = 20) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8-sig", errors="replace")
