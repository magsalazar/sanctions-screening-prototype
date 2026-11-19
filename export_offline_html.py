import json
import os
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

import app as sanctions_app


def _json_for_html(value):
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def build_html(page, records, country_aliases, generated_at):
    css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
    translations = (ROOT / "static" / "i18n.js").read_text(encoding="utf-8")
    offline_search = (ROOT / "static" / "offline_search.js").read_text(encoding="utf-8")

    page = re.sub(
        r'<link rel="stylesheet" href="[^"]+">',
        lambda _: f"<style>\n{css}\n</style>",
        page,
        count=1,
    )
    page = page.replace(
        'data-i18n="documentTitle">OCHA sanctions search prototype',
        'data-i18n="offlineDocumentTitle">OCHA sanctions search · Offline snapshot',
        1,
    )
    page = page.replace('data-i18n="liveData"', 'data-i18n="offlineSnapshot"', 1)
    page = page.replace(
        '  <main class="container main-shell">',
        '  <main class="container main-shell">\n'
        '    <aside class="notice-box" id="snapshot-notice" '
        f'data-generated-at="{generated_at}"></aside>',
        1,
    )
    page = re.sub(
        r'<section id="partner-certification"[\s\S]*?</section>\s*',
        "",
        page,
        count=1,
    )
    page = re.sub(
        r'\s*<a href="/certification" class="local-certification-link"[^>]*>.*?</a>',
        "",
        page,
        count=1,
    )
    page = re.sub(
        r'\s*<script src="/static/country_autocomplete\.js[^"]*"></script>',
        "",
        page,
        count=1,
    )
    page = re.sub(
        r'\s*<script src="/static/certification\.js[^"]*"></script>',
        "",
        page,
        count=1,
    )
    page = re.sub(
        r'\s*<p id="refresh-message"[^>]*></p>',
        "",
        page,
        count=1,
    )
    page = re.sub(
        r'\s*<button type="button" class="refresh-button"[^>]*>.*?</button>',
        "",
        page,
        flags=re.DOTALL,
    )

    scripts = (
        '<script id="offline-records" type="application/json">'
        + _json_for_html(records)
        + "</script>\n"
        '<script id="offline-country-aliases" type="application/json">'
        + _json_for_html(country_aliases)
        + "</script>\n"
        f"<script>\n{translations}\n</script>\n"
        f"<script>\n{offline_search}\n</script>"
    )
    page, replacements = re.subn(
        r'<script src="/static/i18n\.js[^"]*"></script>\s*<script>.*?</script>',
        lambda _: scripts,
        page,
        count=1,
        flags=re.DOTALL,
    )
    if replacements != 1:
        raise RuntimeError("Could not replace the live-app scripts in the page template")
    if "/static/" in page or "fetch(" in page:
        raise RuntimeError("The offline export still contains a server dependency")
    return "\n".join(line.rstrip() for line in page.splitlines()) + "\n"


def export(output_path):
    database_path = Path(sanctions_app.DB)
    if not database_path.is_absolute():
        database_path = ROOT / database_path
    if not database_path.is_file():
        raise FileNotFoundError(f"Sanctions database not found: {database_path}")

    with sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        records = [
            dict(row)
            for row in connection.execute(
                """
                SELECT id, source, source_ref, name, aliases, country, entity_type,
                       programmes, source_url, retrieved_at
                FROM records
                ORDER BY name COLLATE NOCASE, source, source_ref, id
                """
            )
        ]
    if not records:
        raise RuntimeError("The sanctions database contains no records to package")

    response = sanctions_app.app.test_client().get("/")
    if response.status_code != 200:
        raise RuntimeError(f"Could not render the search page (HTTP {response.status_code})")
    generated_at = datetime.now().astimezone().strftime("%d %b %Y, %H:%M %Z")
    page = build_html(
        response.get_data(as_text=True),
        records,
        sanctions_app.COUNTRY_SEARCH_ALIASES,
        generated_at,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(page, encoding="utf-8", newline="")
    return len(records), output_path.stat().st_size


if __name__ == "__main__":
    offline_package = ROOT / "OCHA_Sanctions_Search_Offline.html"
    pages_entry_point = ROOT / "index.html"
    record_count, file_size = export(offline_package)
    shutil.copyfile(offline_package, pages_entry_point)
    print(f"Created {offline_package.name}: {record_count:,} records, {file_size:,} bytes")
    print(f"Created {pages_entry_point.name} for GitHub Pages")
