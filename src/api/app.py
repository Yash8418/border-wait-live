"""Read API, served from a Lambda Function URL.

Routes (GET only):
    /crossings                       latest reading for every crossing
    /crossings/{id}                  latest reading for one crossing
    /crossings/{id}/history          readings in a time range
        ?from=2026-11-05T00:00:00Z   (default: 24 hours ago)
        &to=2026-11-06T00:00:00Z     (default: now)
        &limit=500                   (max 2000)
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

from collector.storage import LATEST_PK, history_pk, to_utc_iso

MAX_LIMIT = 2000
MAX_RANGE = timedelta(days=31)
CROSSING_ID = re.compile(r"^[a-z0-9-]{1,80}$")
INTERNAL_KEYS = {"pk", "sk"}
ROUTES = ["/crossings", "/crossings/{id}", "/crossings/{id}/history"]

_table = None


def get_table():
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
    return _table


class BadRequest(Exception):
    pass


def _json_default(value):
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError(f"Not JSON serialisable: {type(value).__name__}")


def respond(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Cache-Control": "public, max-age=60" if status == 200 else "no-store",
        },
        "body": json.dumps(body, default=_json_default),
    }


def clean(item: dict) -> dict:
    return {key: value for key, value in item.items() if key not in INTERNAL_KEYS}


def parse_time(value: str | None, default: datetime) -> datetime:
    if not value:
        return default
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise BadRequest(f"Invalid timestamp: {value}") from None
    if parsed.tzinfo is None:
        raise BadRequest("Timestamps must include a timezone, e.g. 2026-11-05T00:00:00Z")
    return parsed


def list_latest(table) -> dict:
    items, kwargs = [], {"KeyConditionExpression": Key("pk").eq(LATEST_PK)}
    while True:
        page = table.query(**kwargs)
        items.extend(page["Items"])
        if "LastEvaluatedKey" not in page:
            break
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    crossings = sorted((clean(item) for item in items), key=lambda c: (c.get("location", ""), c["office"]))
    return {"count": len(crossings), "crossings": crossings}


def get_latest(table, crossing_id: str) -> dict | None:
    item = table.get_item(Key={"pk": LATEST_PK, "sk": crossing_id}).get("Item")
    return clean(item) if item else None


def get_history(table, crossing_id: str, params: dict) -> dict:
    now = datetime.now(UTC)
    end = parse_time(params.get("to"), now)
    start = parse_time(params.get("from"), end - timedelta(hours=24))
    if start >= end:
        raise BadRequest("'from' must be before 'to'")
    if end - start > MAX_RANGE:
        raise BadRequest("The time range can be at most 31 days")
    try:
        limit = int(params.get("limit", 500))
    except ValueError:
        raise BadRequest("'limit' must be a number") from None
    if not 1 <= limit <= MAX_LIMIT:
        raise BadRequest(f"'limit' must be between 1 and {MAX_LIMIT}")

    page = table.query(
        KeyConditionExpression=Key("pk").eq(history_pk(crossing_id))
        & Key("sk").between(to_utc_iso(start), to_utc_iso(end)),
        Limit=limit,
    )
    readings = [clean(item) for item in page["Items"]]
    return {
        "crossing_id": crossing_id,
        "from": to_utc_iso(start),
        "to": to_utc_iso(end),
        "count": len(readings),
        "truncated": "LastEvaluatedKey" in page,
        "readings": readings,
    }


def handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    if method != "GET":
        return respond(405, {"error": "Only GET requests are supported"})

    parts = [part for part in event.get("rawPath", "/").split("/") if part]
    params = event.get("queryStringParameters") or {}
    table = get_table()

    try:
        if parts == ["crossings"]:
            return respond(200, list_latest(table))
        if len(parts) in (2, 3) and parts[0] == "crossings":
            crossing_id = parts[1]
            if not CROSSING_ID.match(crossing_id):
                return respond(404, {"error": "Crossing not found"})
            if len(parts) == 2:
                latest = get_latest(table, crossing_id)
                return respond(200, latest) if latest else respond(404, {"error": "Crossing not found"})
            if parts[2] == "history":
                return respond(200, get_history(table, crossing_id, params))
        return respond(404, {"error": "Not found", "routes": ROUTES})
    except BadRequest as error:
        return respond(400, {"error": str(error)})
