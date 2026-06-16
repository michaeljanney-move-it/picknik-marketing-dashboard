#!/usr/bin/env python3
"""Pull lead-type counts and deal-stage counts from HubSpot.

Writes docs/data/hubspot.json. Lead-type definitions, goals, and the
deal pipeline/stage IDs live in config/goals.json — edit that file, not this one.

Env vars:
  HUBSPOT_TOKEN  Private app token (required unless MOCK_DATA=1)
  MOCK_DATA=1    Write realistic sample data instead of calling the API
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config" / "goals.json").read_text())
OUT = ROOT / "docs" / "data" / "hubspot.json"
API = "https://api.hubapi.com/crm/v3/objects/{obj}/search"

MAX_RETRIES = 6  # ~1+2+4+8+16+32s of backoff in the worst case


def post_json(session: requests.Session, url: str, payload: dict) -> dict:
    """POST returning parsed JSON, retrying on 429 (rate limit) and transient
    5xx errors with exponential backoff. HubSpot's search API has a tight
    per-second limit, so back-to-back searches can briefly get throttled."""
    for attempt in range(MAX_RETRIES):
        resp = session.post(url, json=payload, timeout=30)
        if resp.status_code == 429 or 500 <= resp.status_code < 600:
            if attempt == MAX_RETRIES - 1:
                resp.raise_for_status()
            # Honour Retry-After when present, otherwise exponential backoff.
            try:
                retry_after = float(resp.headers.get("Retry-After", ""))
            except ValueError:
                retry_after = 0.0
            time.sleep(max(retry_after, 2 ** attempt))
            continue
        resp.raise_for_status()
        return resp.json()
    resp.raise_for_status()
    return resp.json()


def month_start_ms() -> int:
    now = datetime.now(timezone.utc)
    return int(now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)


def search_total(session: requests.Session, obj: str, filters: list) -> int:
    """Return total record count for a filter set (we only need `total`)."""
    body = post_json(session, API.format(obj=obj), {
        "filterGroups": [{"filters": filters}],
        "limit": 1,
        "properties": ["hs_object_id"],
    })
    return body["total"]


def fetch() -> dict:
    token = os.environ["HUBSPOT_TOKEN"]
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}"})
    since = month_start_ms()

    lead_types = fetch_lead_sources(s, since)

    stages = []
    for st in CONFIG["dealStages"]:
        count = search_total(s, "deals", [
            {"propertyName": "pipeline", "operator": "EQ", "value": CONFIG["dealPipeline"]},
            {"propertyName": "dealstage", "operator": "EQ", "value": st["stageId"]},
        ])
        stages.append({"label": st["label"], "goal": st["goal"], "count": count})

    origins = fetch_deal_origins(s)

    return {"leadTypes": lead_types, "dealStages": stages, "dealOrigins": origins}


def fetch_lead_sources(s: requests.Session, since_ms: int) -> list:
    """Break down contacts created this month by their lead source property
    (PickNik tracks how leads found them in a custom dropdown, default
    `discovery_source`). Returns the top-N sources by volume as cards.
    Contacts with no source set are ignored."""
    prop = CONFIG.get("leadSourceProperty", "discovery_source")
    top_n = CONFIG.get("leadSourceTopN", 6)
    by_source, after, pages = {}, None, 0
    while pages < 30:
        payload = {
            "filterGroups": [{"filters": [
                {"propertyName": "createdate", "operator": "GTE", "value": str(since_ms)}
            ]}],
            "limit": 100,
            "properties": [prop],
        }
        if after:
            payload["after"] = after
        body = post_json(s, API.format(obj="contacts"), payload)
        for c in body.get("results", []):
            value = (c.get("properties") or {}).get(prop)
            if value:
                by_source[value] = by_source.get(value, 0) + 1
        after = (body.get("paging") or {}).get("next", {}).get("after")
        pages += 1
        if not after:
            break
    ranked = sorted(by_source.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    return [{"key": name, "label": name, "goal": None, "count": count}
            for name, count in ranked]


def fetch_deal_origins(s: requests.Session) -> dict:
    """Count deals created since CONFIG['dealOriginSince'] grouped by origin."""
    since = CONFIG.get("dealOriginSince", "2026-05-01")
    since_ms = int(datetime.fromisoformat(since).replace(
        tzinfo=timezone.utc).timestamp() * 1000)
    by_origin, after, pages, total = {}, None, 0, 0
    while pages < 30:
        payload = {
            "filterGroups": [{"filters": [
                {"propertyName": "createdate", "operator": "GTE", "value": str(since_ms)}
            ]}],
            "limit": 100,
            "properties": ["origin"],
        }
        if after:
            payload["after"] = after
        body = post_json(s, API.format(obj="deals"), payload)
        for d in body.get("results", []):
            total += 1
            name = (d.get("properties") or {}).get("origin") or "(not set)"
            if name.startswith("Outbound"):
                name = "Outbound"
            by_origin[name] = by_origin.get(name, 0) + 1
        after = (body.get("paging") or {}).get("next", {}).get("after")
        pages += 1
        if not after:
            break
    counts = sorted(({"name": k, "count": n} for k, n in by_origin.items()),
                    key=lambda c: c["count"], reverse=True)
    return {"since": since, "totalDeals": total, "counts": counts}


def mock() -> dict:
    return {
        "leadTypes": [
            {"key": "mql", "label": "MQL", "goal": 10, "count": 7},
            {"key": "obql", "label": "ObQL", "goal": 10, "count": 4},
            {"key": "event_leads", "label": "Event Leads", "goal": None, "count": 12},
            {"key": "referrals", "label": "Referrals", "goal": None, "count": 3},
        ],
        "dealStages": [
            {"label": "1. Qualifying", "goal": 50, "count": 38},
            {"label": "2. Qualified (BANT)", "goal": 20, "count": 14},
            {"label": "3. Proposing & Negotiating", "goal": 10, "count": 6},
            {"label": "4. Closing & Contracting", "goal": 3, "count": 2},
        ],
    }


def main() -> int:
    data = mock() if os.environ.get("MOCK_DATA") == "1" else fetch()
    data["updatedAt"] = datetime.now(timezone.utc).isoformat()
    data["period"] = datetime.now(timezone.utc).strftime("%B %Y")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2))
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
