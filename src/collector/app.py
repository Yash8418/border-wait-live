"""Lambda entry point: download the live feed and store new readings."""

from __future__ import annotations

import json
import logging
import os

import boto3

from collector.feed import FEED_URL, download_feed, parse_feed
from collector.storage import save_readings

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_table = None


def get_table():
    # Created once per Lambda container and reused across invocations.
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
    return _table


def handler(event, context):
    text = download_feed(os.environ.get("FEED_URL", FEED_URL))
    readings, errors = parse_feed(text)
    for error in errors:
        logger.warning("Skipped feed line: %s", error)

    result = save_readings(get_table(), readings)
    summary = {
        "crossings_in_feed": len(readings),
        "new_readings": result.written,
        "unchanged": result.unchanged,
        "skipped_lines": len(errors),
    }
    logger.info(json.dumps(summary))
    return summary
