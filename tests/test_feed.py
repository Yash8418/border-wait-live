from datetime import timedelta
from pathlib import Path

import pytest

from collector.feed import Wait, parse_feed, parse_timestamp, parse_wait, slugify

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "bwt-eng.csv"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("No Delay", Wait("reported", 0)),
        ("5 minutes", Wait("reported", 5)),
        ("1 minute", Wait("reported", 1)),
        ("45", Wait("reported", 45)),
        ("--", Wait("not_reported", None)),
        ("Closed", Wait("closed", None)),
        ("Temporarily closed", Wait("closed", None)),
        ("Not Applicable", Wait("not_applicable", None)),
        ("???", Wait("unknown", None)),
    ],
)
def test_parse_wait(raw, expected):
    assert parse_wait(raw) == expected


@pytest.mark.parametrize(
    "raw, offset_hours",
    [
        ("2026-11-04 23:15 EST", -5),
        ("2026-11-05 00:15 AST", -4),
        ("2026-10-16 10:33 ADT", -3),
        ("2026-07-01 08:00 PDT", -7),
        ("2026-07-01 08:00 NDT", -2.5),
    ],
)
def test_parse_timestamp_uses_crossing_timezone(raw, offset_hours):
    assert parse_timestamp(raw).utcoffset() == timedelta(hours=offset_hours)


def test_parse_timestamp_rejects_unknown_zone():
    with pytest.raises(ValueError):
        parse_timestamp("2026-11-04 23:15 XYZ")


def test_slugify():
    assert slugify("Gordie Howe International Bridge") == "gordie-howe-international-bridge"
    assert slugify("St. Stephen 3rd Bridge") == "st-stephen-3rd-bridge"


def test_parse_real_feed_sample():
    readings, errors = parse_feed(SAMPLE.read_text(encoding="utf-8"))
    assert errors == []
    assert len(readings) >= 25
    windsor = {r.crossing_id for r in readings if r.location.startswith("Windsor")}
    assert {"ambassador-bridge", "windsor-and-detroit-tunnel", "gordie-howe-international-bridge"} <= windsor
    assert all(r.observed_at.tzinfo is not None for r in readings)


def test_bad_lines_are_reported_not_fatal():
    text = (
        "﻿Customs Office;; Location;; Last updated;; a;; b;; c;; d;;\n"
        "Good;; Somewhere;; 2026-11-04 23:15 EST;; No Delay;; --;; 5 minutes;; --;;\n"
        "Too short;; x\n"
        "Bad time;; Somewhere;; yesterday;; No Delay;; --;; No Delay;; --;;\n"
    )
    readings, errors = parse_feed(text)
    assert [r.office for r in readings] == ["Good"]
    assert readings[0].travellers_canada == Wait("reported", 5)
    assert len(errors) == 2
