#!/usr/bin/env python3
"""Pull website visit data from Leadfeeder (Dealfront).

Writes docs/data/leadfeeder.json: daily visit counts for the last 30 days
plus the top identified companies by visits.

Env vars:
  LEADFEEDER_TOKEN  API token from Leadfeeder Settings -> API
  MOCK_DATA=1       Write realistic sample data instead of calling the API
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "data" / "leadfeeder.json"
BASE = "https://api.leadfeeder.com"
DAYS = 30


def fetch() -> dict:
    token = os.environ["LEADFEEDER_TOKEN"]
    s = requests.Session()
    s.headers.update({"Authorization": f"Token token={token}"})

    accounts = s.get(f"{BASE}/accounts", timeout=30)
    accounts.raise_for_status()
    account_id = accounts.json()["data"][0]["id"]

    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=DAYS)

    # Paginate through leads (identified companies) for the window
    leads, page = [], 1
    while True:
        r = s.get(f"{BASE}/accounts/{account_id}/leads", params={
            "start_date": start.isoformat(), "end_date": end.isoformat(),
            "page[number]": page, "page[size]": 100,
        }, timeout=30)
        r.raise_for_status()
        body = r.json()
        leads.extend(body["data"])
        if not body.get("links", {}).get("next"):
            break
        page += 1

    companies = sorted(
        ({
            "name": l["attributes"].get("name", "Unknown"),
            "visits": l["attributes"].get("visits", 0),
            "industry": l["attributes"].get("industry"),
        } for l in leads),
        key=lambda c: c["visits"], reverse=True,
    )[:15]

    # Daily visit totals from per-lead visit data
    by_day = {}
    for l in leads:
        for v in l["attributes"].get("visits_by_date", []) or []:
            by_day[v["date"]] = by_day.get(v["date"], 0) + v.get("count", 1)
    days = [(start + timedelta(days=i)).isoformat() for i in range(DAYS + 1)]
    daily = [{"date": d, "visits": by_day.get(d, 0)} for d in days]

    return {
        "identifiedCompanies": len(leads),
        "topCompanies": companies,
        "dailyVisits": daily,
    }


def mock() -> dict:
    import random
    random.seed(42)
    end = datetime.now(timezone.utc).date()
    daily = [{"date": (end - timedelta(days=DAYS - i)).isoformat(),
              "visits": random.randint(8, 45)} for i in range(DAYS + 1)]
    return {
        "identifiedCompanies": 87,
        "topCompanies": [
            {"name": "Acme Robotics", "visits": 23, "industry": "Industrial Automation"},
            {"name": "Globex Manufacturing", "visits": 18, "industry": "Manufacturing"},
            {"name": "Initech Systems", "visits": 14, "industry": "Software"},
            {"name": "Umbrella Logistics", "visits": 11, "industry": "Logistics"},
            {"name": "Stark Industries", "visits": 9, "industry": "Aerospace & Defense"},
        ],
        "dailyVisits": daily,
    }


def main() -> int:
    data = mock() if os.environ.get("MOCK_DATA") == "1" else fetch()
    data["updatedAt"] = datetime.now(timezone.utc).isoformat()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=2))
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
