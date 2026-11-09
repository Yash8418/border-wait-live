from dataclasses import replace
from datetime import UTC, datetime, timedelta

from boto3.dynamodb.conditions import Key

import collector.app as app
from collector.feed import parse_feed
from collector.storage import LATEST_PK, history_pk, save_readings, to_utc_iso
from tests.conftest import SAMPLE_TEXT


def sample_readings():
    readings, _ = parse_feed(SAMPLE_TEXT)
    return readings


def test_to_utc_iso_converts_local_time():
    bridge = next(r for r in sample_readings() if r.crossing_id == "ambassador-bridge")
    # 2026-11-04 23:15 EST is 04:15 UTC the next day.
    assert to_utc_iso(bridge.observed_at) == "2026-11-05T04:15:00Z"


def test_save_readings_writes_history_once(table):
    readings = sample_readings()
    first = save_readings(table, readings)
    assert first.written == len(readings) and first.unchanged == 0

    second = save_readings(table, readings)
    assert second.written == 0 and second.unchanged == len(readings)
    history = table.query(KeyConditionExpression=Key("pk").eq(history_pk("ambassador-bridge")))
    assert history["Count"] == 1


def test_latest_items_cover_every_crossing(table):
    readings = sample_readings()
    save_readings(table, readings)
    latest = table.query(KeyConditionExpression=Key("pk").eq(LATEST_PK))["Items"]
    assert {item["sk"] for item in latest} == {r.crossing_id for r in readings}


def test_latest_item_moves_forward_but_never_back(table):
    bridge = next(r for r in sample_readings() if r.crossing_id == "ambassador-bridge")
    newer = replace(bridge, observed_at=bridge.observed_at + timedelta(minutes=15))
    older = replace(bridge, observed_at=bridge.observed_at - timedelta(hours=1))

    save_readings(table, [bridge])
    save_readings(table, [newer])
    save_readings(table, [older])  # e.g. a delayed retry

    latest = table.get_item(Key={"pk": LATEST_PK, "sk": "ambassador-bridge"})["Item"]
    assert latest["observed_at"] == "2026-11-05T04:30:00Z"
    history = table.query(KeyConditionExpression=Key("pk").eq(history_pk("ambassador-bridge")))
    assert history["Count"] == 3


def test_stored_item_shape(table):
    save_readings(table, sample_readings(), collected_at=datetime(2026, 11, 5, 5, 0, tzinfo=UTC))
    item = table.get_item(Key={"pk": history_pk("ambassador-bridge"), "sk": "2026-11-05T04:15:00Z"})["Item"]
    assert item["office"] == "Ambassador Bridge"
    assert item["travellers_canada_status"] == "reported"
    assert item["travellers_canada_min"] == 0
    assert item["travellers_us_status"] == "not_reported"
    assert "travellers_us_min" not in item  # missing values aren't stored as zero
    assert item["collected_at"] == "2026-11-05T05:00:00Z"


def test_handler_end_to_end(table, monkeypatch):
    monkeypatch.setattr(app, "_table", None)
    monkeypatch.setattr(app, "download_feed", lambda url: SAMPLE_TEXT)

    summary = app.handler({}, None)
    assert summary["new_readings"] == summary["crossings_in_feed"] >= 25
    assert summary["skipped_lines"] == 0
    assert app.handler({}, None)["new_readings"] == 0
