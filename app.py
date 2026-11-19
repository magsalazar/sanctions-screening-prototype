import json
import os
import sqlite3
import unicodedata
from contextlib import closing
from pathlib import Path

from flask import Flask, jsonify, render_template, request
from rapidfuzz import fuzz, process, utils

from config import SOURCE_DETAILS, SOURCE_PAGES, SOURCES
from ingest import DB, SourceNotConfigured, init, refresh


def country_alias_key(value):
    normalized = unicodedata.normalize("NFKD", value).casefold()
    return "".join(
        character
        for character in normalized
        if not unicodedata.combining(character) and character.isalnum()
    )


FUZZY_MATCH_THRESHOLD = 75.0


def _normalized_name(value):
    normalized = unicodedata.normalize("NFKD", value).casefold()
    unaccented = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )
    return " ".join(
        "".join(character if character.isalnum() else " " for character in unaccented).split()
    )


def _candidate_similarity(normalized_query, normalized_candidate):
    if not normalized_query:
        return 0.0, False
    if normalized_query in normalized_candidate:
        return 100.0, True
    query_tokens = normalized_query.split()
    candidate_tokens = normalized_candidate.split()
    if not candidate_tokens:
        return 0.0, False
    token_scores = [
        max(fuzz.ratio(query_token, candidate_token) for candidate_token in candidate_tokens)
        for query_token in query_tokens
    ]
    coverage = min(len(query_tokens), len(candidate_tokens)) / max(
        len(query_tokens), len(candidate_tokens)
    )
    return sum(token_scores) / len(token_scores) * coverage, False


DEMOCRATIC_REPUBLIC_OF_CONGO = "Democratic Republic of the Congo"
REPUBLIC_OF_THE_CONGO = "Republic of the Congo"
COUNTRY_NAME_VARIANTS = {
    DEMOCRATIC_REPUBLIC_OF_CONGO: (
        "Congo (Democratic Republic)",
        "Congo, Democratic Republic of",
        "Congo, Democratic Republic of the",
        DEMOCRATIC_REPUBLIC_OF_CONGO,
    ),
    REPUBLIC_OF_THE_CONGO: (
        "Congo",
        "Congo, Republic of",
        "Congo, Republic of the",
        REPUBLIC_OF_THE_CONGO,
    ),
    "Bahamas": ("Bahamas, The", "Bahamas"),
    "Belarus": (
        "Belarusian SSR, (now Belarus)",
        "Former USSR (now Belarus)",
        "Former USSR Currently Belarus",
        "Former USSR Now Belarus",
        "Former USSR, currently Belarus",
        "Former USSR, now Belarus",
        "Belarus",
    ),
    "Myanmar": ("Burma", "Myanmar"),
    "Hong Kong": (
        "China, Hong Kong Special Administrative Region",
        "Hong Kong SAR, China",
        "Hong Kong",
    ),
    "Côte d'Ivoire": ("Cote d Ivoire", "Cote d'Ivoire", "Côte d'Ivoire"),
    "Curaçao": ("Curacao", "Curaçao"),
    "Czechia": ("Czech Republic", "Czechia"),
    "Korea, North": (
        "Democratic People's Republic of Korea",
        "DPRK",
        "North Korea",
        "Korea, North",
    ),
    "Korea, South": ("Korea, Republic of", "Korea, South"),
    "Egypt": ("Egypt, Arab Republic of", "Egypt"),
    "Iran": (
        "Iran (Islamic Republic of)",
        "Iran, Islamic Republic of",
        "Iran",
    ),
    "Kazakhstan": (
        "Kazakh Soviet Socialist Republic",
        "Kazakh Soviet Socialist Republic (now Kazakhstan)",
        "Kazakh SSR",
        "Kazakhstan",
    ),
    "Kyrgyzstan": (
        "Kyrgyz Republic",
        "Former USSR, now Kyrgyzstan",
        "Kyrgyzstan",
    ),
    "Laos": ("Lao People's Democratic Republic", "Laos"),
    "Isle of Man": ("Man, Isle of", "Isle of Man"),
    "North Macedonia": ("North Macedonia, The Republic of", "North Macedonia"),
    "State of Palestine": (
        "Occupied Palestinian Territories",
        "Palestinian",
        "State of Palestine",
    ),
    "Russia": (
        "Russian Federation",
        "Russia (USSR)",
        "Russian SFSR, (now Russian Federation)",
        "Russian Soviet Federative Socialist Republic (RSFSR)",
        "USSR (now Russian Federation)",
        "Yakut Autonomous SSR",
        "Russia",
    ),
    "Somalia": ("Somalia, Federal Republic of", "Somalia"),
    "Syria": ("Syrian Arab Republic", "Syria"),
    "Taiwan": ("Taiwan, China", "Taiwan"),
    "Tanzania": ("United Republic of Tanzania", "Tanzania"),
    "Türkiye": ("Turkey", "Turkiye", "Türkiye"),
    "Ukraine": (
        "Former USSR Currently Ukraine",
        "Former USSR, currently Ukraine",
        "Former USSR, now Ukraine",
        "Ukrainian SSR",
        "Ukrainian SSR (now Ukraine)",
        "Ukraine",
    ),
    "Azerbaijan": ("Former USSR, now Azerbaijan", "Azerbaijan"),
    "Moldova": ("USSR (now Moldova)", "Moldova"),
    "United Kingdom": (
        "United Kingdom of Great Britain and Northern Ireland",
        "United Kingdom",
    ),
    "United States": ("United States of America", "United States"),
    "Venezuela": ("Venezuela, Republica Bolivariana de", "Venezuela"),
    "Viet Nam": ("Vietnam", "Viet Nam"),
    "British Virgin Islands": ("Virgin Islands, British", "British Virgin Islands"),
    "The Gambia": ("Gambia", "The Gambia"),
}
with Path(__file__).with_name("country_aliases.json").open(encoding="utf-8") as aliases_file:
    COUNTRY_LOCALIZED_ALIASES = json.load(aliases_file)["countries"]

COUNTRY_DISPLAY_NAMES = {}
for canonical, aliases in COUNTRY_LOCALIZED_ALIASES.items():
    COUNTRY_DISPLAY_NAMES[country_alias_key(canonical)] = canonical
    for alias in aliases:
        COUNTRY_DISPLAY_NAMES.setdefault(country_alias_key(alias), canonical)
for source_country, variants in COUNTRY_NAME_VARIANTS.items():
    canonical = COUNTRY_DISPLAY_NAMES.get(
        country_alias_key(source_country),
        source_country,
    )
    for variant in variants:
        COUNTRY_DISPLAY_NAMES.setdefault(country_alias_key(variant), canonical)

COUNTRY_EXTRA_ALIASES = {
    DEMOCRATIC_REPUBLIC_OF_CONGO: ("DRC", "RDC", "Democratic Republic of Congo"),
    REPUBLIC_OF_THE_CONGO: ("Congo-Brazzaville", "Congo - Brazzaville"),
    "Central African Republic": ("CAR", "RCA"),
    "Côte d'Ivoire": ("Ivory Coast", "Costa de Marfil"),
    "United States": (
        "US",
        "USA",
        "U.S.",
        "U.S.A.",
        "United States of America",
    ),
    "United Kingdom": ("UK", "U.K.", "GB", "Great Britain", "Britain"),
    "United Arab Emirates": ("UAE", "U.A.E."),
    "Korea, North": ("DPRK", "North Korea"),
    "Korea, South": ("ROK", "South Korea"),
    "Timor-Leste": ("East Timor",),
    "Eswatini": ("Swaziland",),
    "Bolivia": ("Plurinational State of Bolivia",),
    "Venezuela": ("Bolivarian Republic of Venezuela",),
    "Micronesia": ("Federated States of Micronesia",),
    "Brunei": ("Brunei Darussalam",),
    "State of Palestine": (
        "OPT",
        "Palestine",
        "Palestinian Territories",
        "Occupied Palestinian Territory",
    ),
    "Vatican City": ("Vatican", "Vatican City State", "State of Vatican City"),
}

COUNTRY_CANONICAL_NAME_BY_SOURCE = {
    source_country: COUNTRY_DISPLAY_NAMES.get(
        country_alias_key(source_country),
        source_country,
    )
    for source_country in COUNTRY_NAME_VARIANTS
}
COUNTRY_SEARCH_VARIANTS = {
    canonical: tuple(dict.fromkeys((canonical, *aliases)))
    for canonical, aliases in COUNTRY_LOCALIZED_ALIASES.items()
}
for source_country, variants in COUNTRY_NAME_VARIANTS.items():
    canonical = COUNTRY_CANONICAL_NAME_BY_SOURCE[source_country]
    search_terms = list(COUNTRY_SEARCH_VARIANTS.get(canonical, (canonical,)))
    for variant in variants:
        if variant not in search_terms:
            search_terms.append(variant)
    COUNTRY_SEARCH_VARIANTS[canonical] = tuple(search_terms)
for source_country, aliases in COUNTRY_EXTRA_ALIASES.items():
    canonical = COUNTRY_DISPLAY_NAMES.get(
        country_alias_key(source_country),
        source_country,
    )
    search_terms = list(COUNTRY_SEARCH_VARIANTS.get(canonical, (canonical,)))
    for alias in aliases:
        COUNTRY_DISPLAY_NAMES.setdefault(country_alias_key(alias), canonical)
        if alias not in search_terms:
            search_terms.append(alias)
    COUNTRY_SEARCH_VARIANTS[canonical] = tuple(search_terms)

COUNTRY_SEARCH_ALIASES = {}
for canonical, aliases in COUNTRY_LOCALIZED_ALIASES.items():
    search_terms = COUNTRY_SEARCH_VARIANTS[canonical]
    COUNTRY_SEARCH_ALIASES.setdefault(country_alias_key(canonical), search_terms)
    for alias in aliases:
        COUNTRY_SEARCH_ALIASES.setdefault(country_alias_key(alias), search_terms)
for source_country, variants in COUNTRY_NAME_VARIANTS.items():
    canonical = COUNTRY_CANONICAL_NAME_BY_SOURCE[source_country]
    search_terms = COUNTRY_SEARCH_VARIANTS[canonical]
    COUNTRY_SEARCH_ALIASES.setdefault(country_alias_key(source_country), search_terms)
    for alias in variants:
        COUNTRY_SEARCH_ALIASES.setdefault(country_alias_key(alias), search_terms)
for source_country, aliases in COUNTRY_EXTRA_ALIASES.items():
    canonical = COUNTRY_DISPLAY_NAMES.get(
        country_alias_key(source_country),
        source_country,
    )
    search_terms = COUNTRY_SEARCH_VARIANTS[canonical]
    for alias in aliases:
        COUNTRY_SEARCH_ALIASES.setdefault(country_alias_key(alias), search_terms)
COUNTRY_SUGGESTION_ALIASES = {
    DEMOCRATIC_REPUBLIC_OF_CONGO: ("DRC", "RDC"),
    COUNTRY_CANONICAL_NAME_BY_SOURCE[REPUBLIC_OF_THE_CONGO]: (
        REPUBLIC_OF_THE_CONGO,
    ),
    "Central African Republic": ("CAR", "RCA"),
    "Occupied Palestinian Territories": ("OPT",),
    "Holy See": ("Vatican",),
    "South Sudan": (),
}
COUNTRY_AUTOCOMPLETE_ALIASES = {
    canonical: tuple(dict.fromkeys((canonical, *aliases)))
    for canonical, aliases in COUNTRY_LOCALIZED_ALIASES.items()
}
for source_country, variants in COUNTRY_NAME_VARIANTS.items():
    canonical = COUNTRY_CANONICAL_NAME_BY_SOURCE[source_country]
    existing = COUNTRY_AUTOCOMPLETE_ALIASES.get(canonical, (canonical,))
    COUNTRY_AUTOCOMPLETE_ALIASES[canonical] = tuple(
        dict.fromkeys((*existing, source_country, *variants))
    )
for source_country, aliases in COUNTRY_EXTRA_ALIASES.items():
    canonical = COUNTRY_DISPLAY_NAMES.get(
        country_alias_key(source_country),
        source_country,
    )
    existing = COUNTRY_AUTOCOMPLETE_ALIASES.get(canonical, (canonical,))
    COUNTRY_AUTOCOMPLETE_ALIASES[canonical] = tuple(dict.fromkeys((*existing, *aliases)))
SEARCH_PAGE_SIZES = (25, 50, 75, 100)
SEARCH_PAGE_SIZE = 25

app = Flask(__name__)
app.config["SOURCE_REFRESH_ENABLED"] = (
    os.environ.get("SOURCE_REFRESH_ENABLED", "true").casefold() == "true"
)
init()

def ensure_seed_data():
    with closing(sqlite3.connect(DB)) as connection:
        loaded_sources = {
            row[0]
            for row in connection.execute("SELECT DISTINCT source FROM records").fetchall()
        }
    for source in SOURCES:
        if source in loaded_sources:
            continue
        try:
            refresh(source)
        except Exception as exc:
            app.logger.warning("Initial refresh for %s failed: %s", source, exc)
    with closing(sqlite3.connect(DB)) as connection:
        return connection.execute("SELECT COUNT(*) FROM records").fetchone()[0]

def conn():
    connection = sqlite3.connect(DB)
    connection.row_factory = sqlite3.Row
    return connection


def _page_context():
    connection = conn()
    logs = connection.execute("SELECT * FROM refresh_log ORDER BY source").fetchall()
    stats = connection.execute(
        "SELECT COUNT(*) AS records, COUNT(DISTINCT source) AS sources FROM records"
    ).fetchone()
    country_rows = connection.execute(
        "SELECT DISTINCT country FROM records WHERE country IS NOT NULL AND country != ''"
    ).fetchall()
    connection.close()
    logs_by_source = {row["source"]: row for row in logs}
    countries = {}
    for row in country_rows:
        for country in row["country"].split("|"):
            country = country.strip()
            if country and not country.casefold().startswith("region:"):
                display_name = COUNTRY_DISPLAY_NAMES.get(country_alias_key(country), country)
                countries.setdefault(display_name.casefold(), display_name)
    for source_country in COUNTRY_NAME_VARIANTS:
        canonical = COUNTRY_CANONICAL_NAME_BY_SOURCE[source_country]
        countries.setdefault(canonical.casefold(), canonical)
    for canonical in COUNTRY_SUGGESTION_ALIASES:
        countries.setdefault(canonical.casefold(), canonical)
    return {
        "source_details": SOURCE_DETAILS,
        "source_pages": SOURCE_PAGES,
        "sources": SOURCES,
        "logs_by_source": logs_by_source,
        "stats": stats,
        "countries": sorted(countries.values(), key=str.casefold),
        "country_aliases": COUNTRY_SUGGESTION_ALIASES,
        "country_autocomplete_aliases": COUNTRY_AUTOCOMPLETE_ALIASES,
        "source_refresh_enabled": app.config["SOURCE_REFRESH_ENABLED"],
    }


@app.get('/')
def home():
    return render_template("index.html", **_page_context())


@app.get('/certification')
def certification():
    return render_template("certification.html", **_page_context())


@app.get('/api/search')
def search():
    query = " ".join(request.args.get("name", "").split())
    country = request.args.get("country", "").strip()
    source = request.args.get("source", "").strip()
    fuzzy_value = request.args.get("fuzzy_match", "false").strip().casefold()
    if fuzzy_value not in {"true", "false"}:
        return jsonify(error="Fuzzy matching must be true or false"), 400
    fuzzy_match = fuzzy_value == "true" and bool(query)
    requested_page_size = request.args.get(
        "page_size", str(SEARCH_PAGE_SIZE)
    ).strip().casefold()
    valid_page_sizes = {str(size) for size in SEARCH_PAGE_SIZES}
    if requested_page_size != "all" and requested_page_size not in valid_page_sizes:
        return jsonify(error="Page size must be 25, 50, 75, 100, or all"), 400
    show_all = requested_page_size == "all"
    try:
        page = int(request.args.get("page", "1"))
    except ValueError:
        return jsonify(error="Page must be a positive integer"), 400
    if page < 1:
        return jsonify(error="Page must be a positive integer"), 400
    if query and len(query) < 2:
        return jsonify(error="Enter at least 2 characters for a name search"), 400
    if not query and not country:
        return jsonify(error="Enter a name or country to search"), 400
    conditions = []
    args = []
    if query and not fuzzy_match:
        conditions.append("(name LIKE ? OR aliases LIKE ?)")
        args.extend((f"%{query}%", f"%{query}%"))
    if country:
        normalized_country = country_alias_key(country)
        country_terms = COUNTRY_SEARCH_ALIASES.get(normalized_country)
        country_conditions = []
        if country_terms:
            for term in country_terms:
                country_conditions.append(
                    "(country = ? OR country LIKE ? OR country LIKE ? OR country LIKE ?)"
                )
                args.extend(
                    (term, f"{term} |%", f"%| {term} |%", f"%| {term}")
                )
        else:
            country_terms = (country,)
            for term in country_terms:
                country_conditions.append("(country LIKE ? OR country LIKE ?)")
                args.extend((f"{term}%", f"%| {term}%"))
        conditions.append("(" + " OR ".join(country_conditions) + ")")
    if source:
        conditions.append("source=?")
        args.append(source)
    where = " AND ".join(conditions) or "1=1"
    connection = conn()
    if fuzzy_match:
        candidate_rows = connection.execute(
            "SELECT * FROM records WHERE " + where
            + " ORDER BY name COLLATE NOCASE, source, source_ref, id",
            args,
        )
        records_by_id = {}
        choices = []
        choice_record_ids = []
        for candidate_row in candidate_rows:
            record = dict(candidate_row)
            records_by_id[record["id"]] = record
            for candidate in [record["name"], *(record.get("aliases") or "").split("|")]:
                candidate = candidate.strip()
                if candidate:
                    choices.append(candidate)
                    choice_record_ids.append(record["id"])
        normalized_query = _normalized_name(query)
        candidate_matches = process.extract(
            query,
            choices,
            scorer=fuzz.WRatio,
            processor=utils.default_process,
            score_cutoff=FUZZY_MATCH_THRESHOLD,
            limit=None,
        )
        scores_by_id = {}
        for candidate, _, choice_index in candidate_matches:
            record_id = choice_record_ids[choice_index]
            score, exact = _candidate_similarity(
                normalized_query,
                _normalized_name(candidate),
            )
            if exact or score >= FUZZY_MATCH_THRESHOLD:
                previous = scores_by_id.get(record_id)
                if previous is None or exact or score > previous[0]:
                    scores_by_id[record_id] = (100.0 if exact else score, exact)
        ranked_rows = []
        for record_id, (score, exact) in scores_by_id.items():
            record = records_by_id[record_id]
            record["match_type"] = "exact" if exact else "fuzzy"
            record["match_score"] = round(score, 1)
            ranked_rows.append(record)
        ranked_rows.sort(
            key=lambda record: (
                -record["match_score"],
                record["name"].casefold(),
                record["source"],
                record["source_ref"] or "",
                record["id"],
            )
        )
        count = len(ranked_rows)
        page_size = count if show_all else int(requested_page_size)
        total_pages = 1 if show_all else max(
            1, (count + page_size - 1) // page_size
        )
        page = 1 if show_all else min(page, total_pages)
        offset = (page - 1) * page_size
        rows = ranked_rows if show_all else ranked_rows[offset:offset + page_size]
        connection.close()
        return jsonify(
            results=rows,
            count=count,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_previous=page > 1,
            has_next=page < total_pages,
        )
    count = connection.execute(
        "SELECT COUNT(*) FROM records WHERE " + where, args
    ).fetchone()[0]
    page_size = count if show_all else int(requested_page_size)
    total_pages = 1 if show_all else max(
        1, (count + page_size - 1) // page_size
    )
    page = 1 if show_all else min(page, total_pages)
    sql = (
        "SELECT * FROM records WHERE "
        + where
        + " ORDER BY name COLLATE NOCASE, source, source_ref, id"
    )
    if show_all:
        result_rows = connection.execute(sql, args)
    else:
        offset = (page - 1) * page_size
        result_rows = connection.execute(
            sql + " LIMIT ? OFFSET ?",
            args + [page_size, offset],
        )
    rows = [dict(row) for row in result_rows]
    connection.close()
    return jsonify(
        results=rows,
        count=count,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_previous=page > 1,
        has_next=page < total_pages,
    )


@app.post('/api/refresh/<source>')
def do_refresh(source):
    if not app.config["SOURCE_REFRESH_ENABLED"]:
        return jsonify(error="Source refresh is disabled"), 403
    if source not in SOURCES:
        return jsonify(error="Unknown source"), 404
    try:
        return jsonify(source=source, count=refresh(source), status="OK")
    except SourceNotConfigured as exc:
        return jsonify(source=source, status="NOT_CONFIGURED", error=str(exc)), 503
    except Exception as exc:
        return jsonify(source=source, status="ERROR", error=str(exc)), 502


if __name__ == '__main__':
    ensure_seed_data()
    app.run(host='127.0.0.1', port=5000, debug=False)
