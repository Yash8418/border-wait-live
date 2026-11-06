import json
from dataclasses import replace
from datetime import timedelta

import pytest

import api.app as api
from collector.feed import parse_feed
from collector.storage import save_readings
from tests.conftest import SAMPLE_TEXT


def request(path, method="GET", **params):
    event = {"rawPath": path, "requestContext": {"http": {"method": method}}, "queryStringParameters": params or None}
    response = api.handler(event, None)
    return response["statusCode"], json.loads(response["body"])


@pytest.fixture
def loaded(table, monkeypatch):
    monkeypatch.setattr(api, "_table", None)
    readings, _ = parse_feed(SAMPLE_TEXT)
    save_readings(table, readings)
    bridge = next(r for r in readings if r.crossing_id == "ambassador-bridge")
    # Three more hourly readings for the bridge.
    save_readings(table, [replace(bridge, observed_at=bridge.observed_at + timedelta(hours=h)) for h in (1, 2, 3)])
    return readings


def test_list_crossings_returns_latest_for_each(loaded):
    status, body = request("/crossings")
    assert status == 200
    assert body["count"] == len(loaded)
    bridge = next(c for c in body["crossings"] if c["crossing_id"] == "ambassador-bridge")
    assert bridge["observed_at"] == "2026-11-05T07:15:00Z"  # the newest of the four readings
    assert "pk" not in bridge and "sk" not in bridge


def test_get_one_crossing(loaded):
    status, body = request("/crossings/gordie-howe-international-bridge")
    assert status == 200
    assert body["office"] == "Gordie Howe International Bridge"
    assert isinstance(body["travellers_canada_min"], int)


def test_unknown_crossing_is_404(loaded):
    assert request("/crossings/not-a-crossing")[0] == 404
    assert request("/crossings/BAD%20ID")[0] == 404


def test_history_time_range(loaded):
    status, body = request(
        "/crossings/ambassador-bridge/history", **{"from": "2026-11-05T05:00:00Z", "to": "2026-11-05T08:00:00Z"}
    )
    assert status == 200
    assert [r["observed_at"] for r in body["readings"]] == [
        "2026-11-05T05:15:00Z", "2026-11-05T06:15:00Z", "2026-11-05T07:15:00Z",
    ]
    assert body["truncated"] is False


def test_history_limit_marks_truncation(loaded):
    _, body = request(
        "/crossings/ambassador-bridge/history",
        **{"from": "2026-11-05T00:00:00Z", "to": "2026-11-06T00:00:00Z", "limit": "2"},
    )
    assert body["count"] == 2 and body["truncated"] is True


@pytest.mark.parametrize(
    "params, message",
    [
        ({"from": "yesterday"}, "Invalid timestamp"),
        ({"from": "2026-11-05T00:00:00"}, "timezone"),
        ({"from": "2026-11-06T00:00:00Z", "to": "2026-11-05T00:00:00Z"}, "before"),
        ({"from": "2026-09-01T00:00:00Z", "to": "2026-11-05T00:00:00Z"}, "31 days"),
        ({"limit": "0"}, "between"),
        ({"limit": "lots"}, "number"),
    ],
)
def test_history_validation(loaded, params, message):
    status, body = request("/crossings/ambassador-bridge/history", **params)
    assert status == 400
    assert message in body["error"]


def test_only_get_is_allowed(loaded):
    assert request("/crossings", method="POST")[0] == 405


def test_unknown_route(loaded):
    status, body = request("/nope")
    assert status == 404 and "/crossings" in body["routes"]
