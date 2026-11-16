# OCHA sanctions search prototype

The site searches a local SQLite index and links every result to its official source. The ingestion job refreshes the public data feeds; each source has an independent refresh status and a failed refresh does not replace the last successful import.

## Run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python ingest.py
python app.py
```

Open `http://127.0.0.1:5000`. Select EN, FR or ES in the page header; the choice is saved in the browser. Sources can also be refreshed individually from the Source status panel.

## Offline HTML package

After the local database has been refreshed, run:

```powershell
python export_offline_html.py
```

This creates `OCHA_Sanctions_Search_Offline.html`, a self-contained English/French/Spanish search page with the records currently in the database, and a matching root `index.html` for GitHub Pages. Share the offline file through an approved internal location; colleagues should download it and open it in a browser. It does not need Python or a local server.

The HTML is a fixed snapshot: it does not refresh its records, and it has no source-refresh controls. Generate and redistribute a new file after refreshing the database. The source-status panel shows each source's retrieval time. UNGM remains unavailable unless its authorized feed is configured. A result is only a possible match; users must verify it against the official source.

## GitHub Pages

GitHub Pages serves the generated root `index.html` as a static snapshot; it does not run the Flask application or its daily refresh job. Run `python export_offline_html.py` after refreshing the database, then commit and push `index.html` to update the Pages site. This repository and Pages site are public, so the snapshot's indexed names are publicly accessible. The local database, refresh logs, virtual environments, and downloadable offline package are excluded by `.gitignore`. Use approved Python hosting and a managed database for a shared live service.

## Country search aliases

Country suggestions use the UN Statistics Division's [M49 country or area names](https://unstats.un.org/unsd/methodology/m49/) as their baseline, with the requested `Occupied Palestinian Territories` label for Palestine. Search accepts English, French and Spanish names, accent-insensitive typing, common abbreviations, and alternate names such as Tchad for Chad. The localized aliases in `country_aliases.json` are based on [umpirsky/country-list](https://github.com/umpirsky/country-list).

## Daily refresh

The Windows scheduled task `OCHA Sanctions Daily Refresh` runs at **02:30 local time**. It runs under the current Windows user, starts missed runs when the computer becomes available, and writes a dated log to `logs/`. The computer must be on (or wake-capable) and the user must be signed in for the task to run.

To register or change the task on this computer:

```powershell
.\register_daily_refresh.ps1 -Time "02:30"
```

Check its last result with:

```powershell
Get-ScheduledTaskInfo -TaskName "OCHA Sanctions Daily Refresh"
```

To remove it:

```powershell
Unregister-ScheduledTask -TaskName "OCHA Sanctions Daily Refresh"
```

## Connected sources

- **UN Security Council Consolidated List** — official XML.
- **US OFAC SDN** — official CSV, with the OFAC alias and address files joined to the primary entries.
- **US OFAC Consolidated Non-SDN Lists** — official CSV, with the corresponding alias and address files joined.
- **UK Sanctions List** — official CSV; records sharing a UKSL identifier are grouped with their name variants.
- **EU Consolidated Financial Sanctions List** — the Commission's catalogued CSV 1.1 distribution; names, aliases, countries and programmes are grouped by entity.
- **World Bank Ineligible Firms and Individuals** — the JSON endpoint used by the Bank's official list page; only debarred and cross-debarred entries are indexed. The API key is read from the Bank's public page at runtime and is not stored in this project. If the Bank changes its endpoint or page configuration, `WORLD_BANK_API_URL` and `WORLD_BANK_API_KEY` can be set in the process environment.
- **UNGM Ineligibility List** — access-controlled adapter for an authorized HTTPS JSON, CSV or XML feed. UNGM does not expose a verified public feed to this prototype, so a connection is active only after an authorized endpoint and bearer token are supplied.

Set UNGM integration details in the environment before launching the app or running ingestion. Do not put credentials in the repository or paste them into chat:

```powershell
$env:UNGM_API_URL = "https://<authorized-ungm-endpoint>"
$env:UNGM_API_TOKEN = "<authorized-token>"
python ingest.py
```

If no UNGM endpoint/token is configured, the source is shown as `NOT_CONFIGURED`; the rest of the site and sources continue to work. A feed with an unrecognized schema reports an error instead of being indexed as a successful refresh.

## Data handling and limitations

- A refresh is committed only after the complete download and parser succeed. On failure, existing indexed records remain available and the source status shows the error.
- The source status includes the record count, retrieval time and SHA-256 of each imported feed.
- A name match is only a possible match, not a determination. Verify identifiers against the original source.
- The local prototype is not a production screening service. For production, protect refresh operations, use a managed database, add scheduling and alerting, verify licensing/redistribution terms, and complete security/privacy and load testing.
