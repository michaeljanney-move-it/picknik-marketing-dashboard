# PickNik Marketing Dashboard

Static dashboard on GitHub Pages, refreshed daily by GitHub Actions pulling from HubSpot and Leadfeeder.

**What it shows:** monthly lead counts vs. goals (MQL, ObQL, Event Leads, Referrals), open deals per sales stage vs. goals (Qualifying → Contracting), and 30-day website traffic with top identified companies.

## Setup (one time)

1. **Add API secrets** — repo Settings → Secrets and variables → Actions → New repository secret:
   - `HUBSPOT_TOKEN` — HubSpot Settings → Integrations → Private Apps → create app with scopes `crm.objects.contacts.read` and `crm.objects.deals.read`.
   - `LEADFEEDER_TOKEN` — Leadfeeder Settings → API.

2. **Enable Pages** — Settings → Pages → Source: *Deploy from a branch* → Branch `main`, folder `/docs`.

3. **First run** — Actions tab → *Refresh dashboard data* → *Run workflow*. The dashboard appears at
   `https://michaeljanney-move-it.github.io/picknik-marketing-dashboard/` a minute or two later.

After that it refreshes itself daily at 12:00 UTC.

## Configuration

Edit `config/goals.json` — no code changes needed:

- `leadTypes` — each entry is a card on the dashboard. `filters` are HubSpot search filters (contacts created this month are counted). Current assumptions, adjust to taste:
  - **MQL** = lifecycle stage `marketingqualifiedlead`
  - **ObQL** = lifecycle stage `salesqualifiedlead` with original source `OFFLINE` (outbound proxy)
  - **Event Leads** = original source `OTHER_CAMPAIGNS`
  - **Referrals** = original source `REFERRALS`
- `dealStages` — stage IDs are from your real "Product & Services" pipeline. Goals: 50 / 20 / 10 / 3.

## Local testing

```bash
pip install -r requirements.txt
MOCK_DATA=1 python scripts/fetch_hubspot.py
MOCK_DATA=1 python scripts/fetch_leadfeeder.py
python -m http.server -d docs 8000   # open http://localhost:8000
```

With real tokens: `HUBSPOT_TOKEN=… python scripts/fetch_hubspot.py`.

## Adding sources later (GA4, Google Ads, Discourse)

Copy the pattern: a `scripts/fetch_<source>.py` that writes `docs/data/<source>.json`, a secret, a step in `.github/workflows/refresh.yml`, and a section in `docs/index.html`.
