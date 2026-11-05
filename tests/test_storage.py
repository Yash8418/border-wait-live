from datetime import datetime, timezone
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

import collector.app as app
from collector.feed import parse_feed
from collector.storage import save_readings, to_utc_iso

SAMPLE_TEXT = (Path(__file__).resolve().parents[1] / "samples" / "bwt-eng.csv").read_text(encoding="utf-8")
TABLE = "border-wait-readings-test"


@pytest.fixture
def table(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ca-central-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    with mock_aws():
        dynamodb = boto3.resource("dynamodb")
        created = dynamodb.create_table(
            TableName=TABLE,
            KeySchema=[
                {"AttributeName": "crossing_id", "KeyType": "HASH"},
                {"AttributeName": "observed_at", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "crossing_id", "AttributeType": "S"},
                {"AttributeName": "observed_at", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        yield created


def test_to_utc_iso_converts_local_time():
    readings, _ = parse_feed(SAMPLE_TEXT)
    bridge = next(r for r in readings if r.crossing_id == "ambassador-bridge")
    # 2026-11-04 23:15 EST is 04:15 UTC the next day.
    assert to_utc_iso(bridge.observed_at) == "2026-11-05T04:15:00Z"


def test_save_readings_writes_once_and_skips_repeats(table):
    readings, _ = parse_feed(SAMPLE_TEXT)
    first = save_readings(table, readings)
    assert first.written == len(readings) and first.unchanged == 0

    second = save_readings(table, readings)
    assert second.written == 0 and second.unchanged == len(readings)
    assert table.scan()["Count"] == len(readings)


def test_stored_item_shape(table):
    readings, _ = parse_feed(SAMPLE_TEXT)
    save_readings(table, readings, collected_at=datetime(2026, 11, 5, 5, 0, tzinfo=timezone.utc))
    item = table.get_item(Key={"crossing_id": "ambassador-bridge", "observed_at": "2026-11-05T04:15:00Z"})["Item"]
    assert item["office"] == "Ambassador Bridge"
    assert item["travellers_canada_status"] == "reported"
    assert item["travellers_canada_min"] == 0
    assert item["travellers_us_status"] == "not_reported"
    assert "travellers_us_min" not in item  # missing values aren't stored as zero
    assert item["collected_at"] == "2026-11-05T05:00:00Z"


def test_handler_end_to_end(table, monkeypatch):
    monkeypatch.setenv("TABLE_NAME", TABLE)
    monkeypatch.setattr(app, "_table", None)
    monkeypatch.setattr(app, "download_feed", lambda url: SAMPLE_TEXT)

    summary = app.handler({}, None)
    assert summary["new_readings"] == summary["crossings_in_feed"] >= 25
    assert summary["skipped_lines"] == 0
    assert app.handler({}, None)["new_readings"] == 0
