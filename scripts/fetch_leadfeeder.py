#!/usr/bin/env python3
"""Pull website visit data from the Leadfeeder API (v1, X-Api-Key auth).

Writes docs/data/leadfeeder.json: daily visit counts for the last 30 days
plus the top identified companies by visits.

Env vars:
  LEADFEEDER_TOKEN  API key from Leadfeeder Settings -> Personal -> API Keys
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
BASE = "https://api.leadfeeder.com/v1"
DAYS = 30
MAX_PAGES = 20  # x100 = up to 2000 visits per refresh


def fetch() -> dict:
    api_key = os.environ["LEADFEEDER_TOKEN"].strip()
    s = requests.Session()
    s.headers.update({
        "X-Api-Key": api_key,
        "User-Agent": "picknik-marketing-dashboard",
    })

    accounts = s.get(f"{BASE}/accounts", timeout=30)
    accounts.raise_for_status()
    account_id = accounts.json()["data"][0]["id"]

    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=DAYS)

    # Page through web visits in the window (company data attached)
    visits, included, page = [], {}, 1
    while page <= MAX_PAGES:
        r = s.post(
            f"{BASE}/web-visits",
            params={"account_id": account_id, "include": "company",
                    "page[num]": page, "page[size]": 100},
            json={"start_date": start.isoformat(), "end_date": end.isoformat()},
            timeout=30,
        )
        r.raise_for_status()
        body = r.json()
        visits.extend(body.get("data", []))
        for inc in body.get("included", []) or []:
            included[(inc.get("type"), inc.get("id"))] = inc
        pagination = body.get("meta", {}).get("pagination", {})
        if page >= pagination.get("page_count", page):
            break
        page += 1

    def company_name(rel):
        if not rel:
            return None
        attrs = rel.get("attributes") or {}
        if attrs.get("name"):
            return attrs["name"]
        inc = included.get(("company", rel.get("id")))
        if inc:
            return (inc.get("attributes") or {}).get("name")
        return None

    # Daily counts + per-company visit counts
    by_day, by_company = {}, {}
    for v in visits:
        attrs = v.get("attributes", {})
        d = (attrs.get("started_at") or "")[:10]
        if d:
            by_day[d] = by_day.get(d, 0) + 1
        rel = (v.get("relationships") or {}).get("company")
        if rel and rel.get("id"):
            cid = rel["id"]
            name = company_name(rel) or f"Company {cid}"
            entry = by_company.setdefault(cid, {"name": name, "visits": 0, "industry": None})
            entry["visits"] += 1
            if name and entry["name"].startswith("Company "):
                entry["name"] = name

    days = [(start + timedelta(days=i)).isoformat() for i in range(DAYS + 1)]
    daily = [{"date": d, "visits": by_day.get(d, 0)} for d in days]
    companies = sorted(by_company.values(), key=lambda c: c["visits"], reverse=True)[:15]

    return {
        "identifiedCompanies": len(by_company),
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
