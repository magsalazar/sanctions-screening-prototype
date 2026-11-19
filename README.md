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

## Search Report demonstration

Open the separate local workflow at `http://127.0.0.1:5000/certification`. It records the requesting organisation and requester details, registers third parties, screens names and aliases through `/api/search`, and lets the reviewer prepare an unsigned Search Report. Country fields reuse the country autocomplete. Source coverage distinguishes searchable indexed snapshots from unavailable sources and failed queries; a partial search is not presented as a completed check.

Fuzzy name matching is optional and off by default. It uses a 75% token-similarity heuristic (for example, `John Kony` can return `Joseph Kony`); scores are not probabilities, identity determinations, or proof. Fuzzy searches can return unrelated names. Review every possible match against the original source.

The report's **Export PDF** button opens the browser's print dialog; choose **Save as PDF**. This creates an unsigned demonstration report only, not an official certificate. Exercise data and results remain in the open browser session; there is no trusted timestamp, persistent audit trail, digital signature, independent verification, or email integration.

Use synthetic data only. Entity names and aliases are sent to the app's search endpoint and may appear in server request logs. Do not enter real partner, personal, or other sensitive information. The app has no user authentication or authorization and is not suitable for real screening or internal use without additional safeguards. The GitHub Pages static snapshot excludes the certification workflow.

## Render demonstration

The `render.yaml` Blueprint configures a public, free Render web service for synthetic-data demonstrations only. Connect this repository to Render and create a Blueprint from a branch containing the application and `render.yaml`; Render will deploy the Flask app and give it an HTTPS address. Open `/certification` on that address for the Search Report workflow. GitHub Pages remains a separate static snapshot and does not run Flask.

The build downloads available source data into SQLite; failures are logged and unavailable sources remain visible as coverage gaps. The build fails if no records load. The database is a snapshot from the build, not a live feed. To refresh it, select **Manual Deploy > Clear build cache & deploy** in Render, and check source status and retrieval dates before demonstrating. The public source-refresh endpoint and its buttons are disabled by the Blueprint; local runs retain the existing refresh controls unless `SOURCE_REFRESH_ENABLED` is set to `false`.

Render's free service sleeps after inactivity and has an ephemeral filesystem. Runtime database changes are lost on restart or spin-down; the built snapshot is restored. Free usage is limited and can incur charges or suspension if included bandwidth or build minutes are exceeded. This service is public and unauthenticated: use synthetic data only, do not enter sensitive information, and do not treat it as a production service. Review access controls, request logging, rate limits, privacy, and licensing before any broader deployment.

## Offline HTML package

After the local database has been refreshed, run:

```powershell
python export_offline_html.py
```

This creates `OCHA_Sanctions_Search_Offline.html`, a self-contained English/French/Spanish search page with the records currently in the database, including opt-in fuzzy name matching, and a matching root `index.html` for GitHub Pages. These static files do not include the local Search Report workflow. Share the offline file through an approved internal location; colleagues should download it and open it in a browser. It does not need Python or a local server.

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
