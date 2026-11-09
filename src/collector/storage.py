"""Store readings in DynamoDB using a single-table design.

    Item type     pk                            sk
    ------------  ----------------------------  ----------------------
    History       CROSSING#ambassador-bridge    2026-11-05T04:15:00Z
    Latest        LATEST                        ambassador-bridge

- One crossing's history in a time range is a single Query on its partition.
- Every crossing's current wait is a single Query on pk = LATEST (no table scans).

CBSA often republishes the same "Last updated" time across several polls, so history
writes are conditional (re-collecting an unchanged reading is a no-op), and the latest
item is only replaced by a newer reading.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from botocore.exceptions import ClientError

from collector.feed import Reading, Wait

LATEST_PK = "LATEST"


def history_pk(crossing_id: str) -> str:
    return f"CROSSING#{crossing_id}"


@dataclass
class WriteResult:
    written: int = 0
    unchanged: int = 0


def to_utc_iso(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _wait_attrs(prefix: str, wait: Wait) -> dict:
    attrs = {f"{prefix}_status": wait.status}
    if wait.minutes is not None:
        attrs[f"{prefix}_min"] = wait.minutes
    return attrs


def reading_attrs(reading: Reading, collected_at: datetime) -> dict:
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


def _is_condition_failure(error: ClientError) -> bool:
    return error.response["Error"]["Code"] == "ConditionalCheckFailedException"


def save_readings(table, readings: list[Reading], collected_at: datetime | None = None) -> WriteResult:
    """Write new readings and keep each crossing's latest item current. `table` is a boto3 Table."""
    collected_at = collected_at or datetime.now(UTC)
    result = WriteResult()
    for reading in readings:
        attrs = reading_attrs(reading, collected_at)
        try:
            table.put_item(
                Item={"pk": history_pk(reading.crossing_id), "sk": attrs["observed_at"], **attrs},
                ConditionExpression="attribute_not_exists(pk)",
            )
            result.written += 1
        except ClientError as error:
            if not _is_condition_failure(error):
                raise
            result.unchanged += 1
            continue

        try:
            table.put_item(
                Item={"pk": LATEST_PK, "sk": reading.crossing_id, **attrs},
                ConditionExpression="attribute_not_exists(pk) OR observed_at < :new",
                ExpressionAttributeValues={":new": attrs["observed_at"]},
            )
        except ClientError as error:
            if not _is_condition_failure(error):  # an older reading never replaces a newer one
                raise
    return result
