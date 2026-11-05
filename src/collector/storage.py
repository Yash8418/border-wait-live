"""Store readings in DynamoDB.

Table design (single table):
    PK  crossing_id   e.g. "ambassador-bridge"
    SK  observed_at   ISO-8601 UTC, e.g. "2026-11-05T04:15:00Z"

Querying one crossing's history by time range is a single Query on the partition.
CBSA often republishes the same "Last updated" time for a crossing across several
polls, so writes are conditional: re-collecting an unchanged reading is a no-op.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from botocore.exceptions import ClientError

from collector.feed import Reading, Wait


@dataclass
class WriteResult:
    written: int = 0
    unchanged: int = 0


def to_utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _wait_attrs(prefix: str, wait: Wait) -> dict:
    attrs = {f"{prefix}_status": wait.status}
    if wait.minutes is not None:
        attrs[f"{prefix}_min"] = wait.minutes
    return attrs


def to_item(reading: Reading, collected_at: datetime) -> dict:
    return {
        "crossing_id": reading.crossing_id,
        "observed_at": to_utc_iso(reading.observed_at),
        "office": reading.office,
        "location": reading.location,
        "observed_local": reading.observed_at.isoformat(),
        "collected_at": to_utc_iso(collected_at),
        **_wait_attrs("travellers_canada", reading.travellers_canada),
        **_wait_attrs("travellers_us", reading.travellers_us),
        **_wait_attrs("commercial_canada", reading.commercial_canada),
        **_wait_attrs("commercial_us", reading.commercial_us),
    }


def save_readings(table, readings: list[Reading], collected_at: datetime | None = None) -> WriteResult:
    """Write readings that haven't been stored before. `table` is a boto3 DynamoDB Table resource."""
    collected_at = collected_at or datetime.now(timezone.utc)
    result = WriteResult()
    for reading in readings:
        try:
            table.put_item(
                Item=to_item(reading, collected_at),
                ConditionExpression="attribute_not_exists(crossing_id) AND attribute_not_exists(observed_at)",
            )
            result.written += 1
        except ClientError as error:
            if error.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
            result.unchanged += 1
    return result
