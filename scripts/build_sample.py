"""Build site/sample/crossings.json from the captured CBSA feed in samples/.

The status page falls back to this file when no API URL is configured, so it can be
previewed (and hosted) before the AWS stack is deployed. The JSON has exactly the
shape of the API's GET /crossings response.

Usage:
    python scripts/build_sample.py
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from api.app import _json_default  # noqa: E402
from collector.feed import parse_feed  # noqa: E402
from collector.storage import reading_attrs  # noqa: E402

FEED = ROOT / "samples" / "bwt-eng.csv"
OUT = ROOT / "site" / "sample" / "crossings.json"


def build(feed_text: str, collected_at: datetime) -> dict:
    readings, _ = parse_feed(feed_text)
    crossings = sorted(
        (reading_attrs(r, collected_at) for r in readings), key=lambda c: (c.get("location", ""), c["office"])
    )
    return {"count": len(crossings), "crossings": crossings}


def main() -> None:
    text = FEED.read_text(encoding="utf-8-sig")
    collected_at = datetime.fromtimestamp(FEED.stat().st_mtime, UTC).replace(microsecond=0)
    data = build(text, collected_at)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=1, default=_json_default) + "\n", encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)} with {data['count']} crossings")


if __name__ == "__main__":
    main()
