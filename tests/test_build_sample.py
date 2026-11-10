from datetime import UTC, datetime
from pathlib import Path

from scripts.build_sample import build

FEED = Path(__file__).resolve().parents[1] / "samples" / "bwt-eng.csv"


def test_sample_matches_the_api_shape():
    data = build(FEED.read_text(encoding="utf-8-sig"), datetime(2026, 11, 5, tzinfo=UTC))
    assert data["count"] == len(data["crossings"]) > 20
    ids = {c["crossing_id"] for c in data["crossings"]}
    assert {"ambassador-bridge", "windsor-and-detroit-tunnel"} <= ids
    first = data["crossings"][0]
    assert {"crossing_id", "office", "location", "observed_at", "travellers_canada_status"} <= first.keys()
    assert "pk" not in first and "sk" not in first
