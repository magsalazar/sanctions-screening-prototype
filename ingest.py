import csv
import hashlib
import io
import json
import os
import re
import sqlite3
import sys
import xml.etree.ElementTree as ET
from collections import OrderedDict
from contextlib import contextmanager
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

from config import MANUAL_SOURCE, SOURCE_PAGES, SOURCES

DB = os.environ.get("SANCTIONS_DB", "sanctions.db")
UA = "OCHA-AIT-Sanctions-Prototype/0.3 (technical prototype)"

OFAC_FILES = {
    "OFAC_SDN": {
        "primary": SOURCES["OFAC_SDN"],
        "aliases": "https://www.treasury.gov/ofac/downloads/alt.csv",
        "addresses": "https://www.treasury.gov/ofac/downloads/add.csv",
    },
    "OFAC_NON_SDN": {
        "primary": SOURCES["OFAC_NON_SDN"],
        "aliases": "https://www.treasury.gov/ofac/downloads/consolidated/cons_alt.csv",
        "addresses": "https://www.treasury.gov/ofac/downloads/consolidated/cons_add.csv",
    },
}


class SourceNotConfigured(Exception):
    pass


@contextmanager
def _db_connection():
    connection = sqlite3.connect(DB)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def norm(value):
    if value is None:
        return ""
    return " ".join(str(value).replace(";"," ").split()).strip()


def _clean(value):
    value = norm(value)
    return "" if value in ("-0-", "0-") else value


def _unique(values):
    found = OrderedDict()
    for value in values:
        value = _clean(value)
        if value:
            found.setdefault(value.casefold(), value)
    return list(found.values())


def init():
    with _db_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS records(
                id INTEGER PRIMARY KEY,
                source TEXT,
                source_ref TEXT,
                name TEXT,
                aliases TEXT,
                country TEXT,
                entity_type TEXT,
                programmes TEXT,
                source_url TEXT,
                retrieved_at TEXT
            );
            CREATE INDEX IF NOT EXISTS ix_name ON records(name);
            CREATE INDEX IF NOT EXISTS ix_source ON records(source);
            CREATE TABLE IF NOT EXISTS refresh_log(
                source TEXT PRIMARY KEY,
                status TEXT,
                count INTEGER,
                message TEXT,
                retrieved_at TEXT,
                sha256 TEXT
            );
            """
        )


def _request(source, url, headers=None, timeout=90):
    request_headers = {"User-Agent": UA, "Accept": "*/*"}
    if headers:
        request_headers.update(headers)
    try:
        response = requests.get(url, timeout=timeout, headers=request_headers)
    except requests.RequestException as exc:
        raise RuntimeError(f"{source} retrieval failed ({type(exc).__name__})") from exc
    if not response.ok:
        raise RuntimeError(f"{source} returned HTTP {response.status_code}")
    if not response.content:
        raise ValueError(f"{source} returned an empty file")
    return response.content


def _csv_rows(data, delimiter=","):
    text = data.decode("utf-8-sig", errors="replace")
    return [
        row
        for row in csv.reader(io.StringIO(text), delimiter=delimiter)
        if any(norm(cell) for cell in row)
    ]


def _xml_name(element):
    return element.tag.rsplit("}", 1)[-1].upper()


def _child_text(element, name):
    name = name.upper()
    for child in list(element):
        if _xml_name(child) == name:
            return norm(child.text)
    return ""


def _descendants(element, name):
    name = name.upper()
    return [child for child in element.iter() if _xml_name(child) == name]


def unsc(data):
    root = ET.fromstring(data)
    output = []
    for kind, record_tag, alias_tag, address_tag in (
        ("Individual", "INDIVIDUAL", "INDIVIDUAL_ALIAS", "INDIVIDUAL_ADDRESS"),
        ("Entity", "ENTITY", "ENTITY_ALIAS", "ENTITY_ADDRESS"),
    ):
        for element in _descendants(root, record_tag):
            if kind == "Individual":
                name = norm(
                    " ".join(
                        filter(
                            None,
                            (
                                _child_text(element, "FIRST_NAME"),
                                _child_text(element, "SECOND_NAME"),
                                _child_text(element, "THIRD_NAME"),
                                _child_text(element, "FOURTH_NAME"),
                            ),
                        )
                    )
                )
            else:
                name = (
                    _child_text(element, "FIRST_NAME")
                    or _child_text(element, "ENTITY_NAME")
                )
            aliases = []
            for alias in _descendants(element, alias_tag):
                aliases.extend(_child_text(alias, name) for name in ("ALIAS_NAME",))
            countries = []
            for address in _descendants(element, address_tag):
                countries.append(_child_text(address, "COUNTRY"))
            if not name:
                name = next(iter(_unique(aliases)), "")
            if not name:
                continue
            output.append(
                {
                    "source": "UNSC",
                    "source_ref": _child_text(element, "REFERENCE_NUMBER"),
                    "name": name,
                    "aliases": " | ".join(
                        value for value in _unique(aliases) if value.casefold() != name.casefold()
                    ),
                    "country": " | ".join(_unique(countries)),
                    "entity_type": kind,
                    "programmes": _child_text(element, "UN_LIST_TYPE"),
                    "source_url": SOURCE_PAGES["UNSC"],
                }
            )
    return output


def ofac_bundle(primary_data, alias_data, address_data, source):
    records = OrderedDict()
    for row in _csv_rows(primary_data):
        if len(row) < 4:
            continue
        record_id, name = _clean(row[0]), _clean(row[1])
        if not record_id or not name:
            continue
        records[record_id] = {
            "source": source,
            "source_ref": record_id,
            "name": name,
            "aliases": [],
            "country": [],
            "entity_type": _clean(row[2]),
            "programmes": [_clean(row[3])],
            "source_url": SOURCE_PAGES[source],
        }

    for row in _csv_rows(alias_data):
        if len(row) < 4:
            continue
        record = records.get(_clean(row[0]))
        if record:
            record["aliases"].append(_clean(row[3]))

    for row in _csv_rows(address_data):
        if len(row) < 5:
            continue
        record = records.get(_clean(row[0]))
        if record:
            record["country"].append(_clean(row[4]))

    output = []
    for record in records.values():
        record["aliases"] = " | ".join(
            value
            for value in _unique(record["aliases"])
            if value.casefold() != record["name"].casefold()
        )
        record["country"] = " | ".join(_unique(record["country"]))
        record["programmes"] = " | ".join(_unique(record["programmes"]))
        output.append(record)
    return output


def uk(data):
    rows = csv.reader(
        io.TextIOWrapper(io.BytesIO(data), encoding="utf-8-sig", errors="replace", newline="")
    )
    header = next(
        (
            row
            for row in rows
            if "unique id" in [norm(cell).casefold() for cell in row]
        ),
        None,
    )
    if header is None:
        return []
    headers = [norm(cell) for cell in header]
    grouped = OrderedDict()
    for row in rows:
        if not any(norm(cell) for cell in row):
            continue
        values = row + [""] * max(0, len(headers) - len(row))
        record = {headers[index]: values[index] for index in range(len(headers))}
        lowered = {key.casefold(): value for key, value in record.items()}

        def get(*keys):
            for key in keys:
                value = lowered.get(key.casefold())
                if value:
                    return _clean(value)
            return ""

        ref = get("Unique ID")
        name = get("Name 6", "Name", "Full Name", "Primary Name")
        if not name:
            name = norm(" ".join(filter(None, (get(f"Name {index}") for index in range(1, 7)))))
        if not name:
            continue
        key = ref or f"{name.casefold()}:{len(grouped)}"
        item = grouped.setdefault(
            key,
            {
                "source": "UK",
                "source_ref": ref,
                "name": name,
                "aliases": [],
                "country": [],
                "entity_type": get("Name type", "Individual, Entity, Ship", "Group Type", "Entity Type"),
                "programmes": [],
                "source_url": SOURCE_PAGES["UK"],
            },
        )
        item["aliases"].append(name)
        item["country"].append(get("Address Country", "Country", "Country of Birth", "Nationality"))
        item["programmes"].append(get("Regime Name", "Regime"))
    output = []
    for item in grouped.values():
        item["aliases"] = " | ".join(
            value
            for value in _unique(item["aliases"])
            if value.casefold() != item["name"].casefold()
        )
        item["country"] = " | ".join(_unique(item["country"]))
        item["programmes"] = " | ".join(_unique(item["programmes"]))
        output.append(item)
    return output


def eu(data):
    reader = csv.DictReader(
        io.StringIO(data.decode("utf-8-sig", errors="replace")),
        delimiter=";",
    )
    if not reader.fieldnames or "Entity_LogicalId" not in reader.fieldnames:
        raise ValueError("EU file does not match the expected consolidated-list CSV schema")
    grouped = OrderedDict()
    for row in reader:
        ref = _clean(row.get("Entity_EU_ReferenceNumber"))
        logical_id = _clean(row.get("Entity_LogicalId"))
        key = logical_id or ref
        name = _clean(row.get("NameAlias_WholeName")) or norm(
            " ".join(
                filter(
                    None,
                    (
                        _clean(row.get("NameAlias_FirstName")),
                        _clean(row.get("NameAlias_MiddleName")),
                        _clean(row.get("NameAlias_LastName")),
                    ),
                )
            )
        )
        if not key or not name:
            continue
        item = grouped.setdefault(
            key,
            {
                "source": "EU",
                "source_ref": ref,
                "name": name,
                "aliases": [],
                "country": [],
                "entity_type": _clean(row.get("Entity_SubjectType_ClassificationCode"))
                or _clean(row.get("Entity_SubjectType")),
                "programmes": [],
                "source_url": SOURCE_PAGES["EU"],
            },
        )
        item["aliases"].append(name)
        item["country"].extend(
            (
                _clean(row.get("Address_CountryDescription")),
                _clean(row.get("Citizenship_CountryDescription")),
                _clean(row.get("BirthDate_CountryDescription")),
            )
        )
        item["programmes"].append(_clean(row.get("Entity_Regulation_Programme")))
    output = []
    for item in grouped.values():
        item["aliases"] = " | ".join(
            value
            for value in _unique(item["aliases"])
            if value.casefold() != item["name"].casefold()
        )
        item["country"] = " | ".join(_unique(item["country"]))
        item["programmes"] = " | ".join(_unique(item["programmes"]))
        output.append(item)
    return output


def world_bank(data):
    payload = json.loads(data.decode("utf-8-sig"))
    rows = payload.get("response", {}).get("ZPROCSUPP")
    if not isinstance(rows, list):
        raise ValueError("World Bank response does not contain the expected supplier list")
    output = []
    for row in rows:
        status = _clean(row.get("SUPP_ELIG_STAT") or row.get("ELIG_STAT")).upper()
        ineligible_flag = _clean(row.get("INELIG_FLG")).upper()
        if ineligible_flag not in {"D", "X"} or status not in {"DEBARRED", "X-DEBARRED"}:
            continue
        name = _clean(row.get("SUPP_NAME"))
        if not name:
            continue
        details = [
            status,
            _clean(row.get("INELIGIBLY_STATUS")),
            _clean(row.get("DEBAR_FROM_DATE")),
            _clean(row.get("DEBAR_TO_DATE")),
            _clean(row.get("DEBAR_REASON")),
        ]
        output.append(
            {
                "source": "WORLD_BANK",
                "source_ref": _clean(row.get("SUPP_ID")),
                "name": name,
                "aliases": "",
                "country": _clean(row.get("COUNTRY_NAME")),
                "entity_type": "Individual" if _clean(row.get("SUPP_TYPE_CODE")).upper() == "I" else "Firm",
                "programmes": " | ".join(_unique(details)),
                "source_url": SOURCE_PAGES["WORLD_BANK"],
            }
        )
    return output


def _world_bank_payload():
    endpoint = os.environ.get("WORLD_BANK_API_URL", "").strip()
    api_key = os.environ.get("WORLD_BANK_API_KEY", "").strip()
    if not endpoint or not api_key:
        page = _request("WORLD_BANK", SOURCE_PAGES["WORLD_BANK"])
        html = page.decode("utf-8", errors="replace")
        endpoint_match = re.search(r'var\s+prodtabApi\s*=\s*["\']([^"\']+)["\']', html)
        key_match = re.search(r'var\s+propApiKey\s*=\s*["\']([^"\']+)["\']', html)
        endpoint = endpoint or (endpoint_match.group(1) if endpoint_match else "")
        api_key = api_key or (key_match.group(1) if key_match else "")
    if not endpoint or not api_key:
        raise SourceNotConfigured(
            "World Bank API endpoint/key could not be resolved; set WORLD_BANK_API_URL and WORLD_BANK_API_KEY"
        )
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or not parsed.hostname or not (
        parsed.hostname == "worldbank.org" or parsed.hostname.endswith(".worldbank.org")
    ):
        raise ValueError("World Bank API endpoint must use HTTPS on a worldbank.org host")
    return _request("WORLD_BANK", endpoint, headers={"apikey": api_key})


def _ungm_rows(payload):
    if isinstance(payload, list):
        if all(isinstance(item, dict) for item in payload):
            return payload
        for item in payload:
            rows = _ungm_rows(item)
            if rows:
                return rows
    elif isinstance(payload, dict):
        for key in ("results", "records", "data", "items", "entities", "suppliers"):
            rows = _ungm_rows(payload.get(key))
            if rows:
                return rows
    return []


def ungm(data):
    content = data.lstrip()
    if content.startswith(b"{") or content.startswith(b"["):
        rows = _ungm_rows(json.loads(data.decode("utf-8-sig")))
    elif content.startswith(b"<"):
        root = ET.fromstring(data)
        rows = []
        for element in root.iter():
            fields = {
                _xml_name(child): norm(child.text)
                for child in list(element)
                if len(list(child)) == 0
            }
            if any(key in fields for key in ("NAME", "ENTITY_NAME", "SUPPLIER_NAME", "VENDOR_NAME")):
                rows.append(fields)
    else:
        text = data.decode("utf-8-sig", errors="replace")
        sample = text[:4096]
        try:
            delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
        except csv.Error:
            delimiter = ","
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        rows = list(reader)
    output = []
    for row in rows:
        lowered = {str(key).strip().casefold().replace(" ", "_"): value for key, value in row.items()}

        def get(*keys):
            for key in keys:
                value = lowered.get(key)
                if isinstance(value, (str, int, float)) and norm(value):
                    return _clean(value)
            return ""

        name = get(
            "name",
            "entity_name",
            "supp_name",
            "supplier_name",
            "vendor_name",
            "firm_name",
            "individual_name",
            "legal_name",
            "primary_name",
            "full_name",
        )
        if not name:
            continue
        output.append(
            {
                "source": "UNGM",
                "source_ref": get("id", "reference", "reference_number", "unique_id", "supplier_id"),
                "name": name,
                "aliases": get("aliases", "alias", "other_names"),
                "country": get("country", "country_name", "nationality"),
                "entity_type": get("entity_type", "type", "subject_type"),
                "programmes": get("status", "reason", "programme", "program"),
                "source_url": SOURCE_PAGES["UNGM"],
            }
        )
    if not output:
        raise ValueError("UNGM response does not contain a recognized name field")
    return output


def _fetch_ofac(source):
    files = OFAC_FILES[source]
    downloaded = []
    for file_type, url in files.items():
        downloaded.append((file_type, _request(source, url)))
    content = {file_type: data for file_type, data in downloaded}
    records = ofac_bundle(
        content["primary"],
        content["aliases"],
        content["addresses"],
        source,
    )
    return records, downloaded


def _fetch_source(source):
    if source in OFAC_FILES:
        return _fetch_ofac(source)
    if source == "UNSC":
        data = _request(source, SOURCES[source])
        return unsc(data), [("unsc", data)]
    if source == "UK":
        data = _request(source, SOURCES[source])
        return uk(data), [("uk", data)]
    if source == "EU":
        data = _request(source, SOURCES[source], timeout=120)
        return eu(data), [("eu", data)]
    if source == "WORLD_BANK":
        data = _world_bank_payload()
        return world_bank(data), [("world_bank", data)]
    if source == MANUAL_SOURCE:
        raise SourceNotConfigured("UNGM must be checked separately")
    raise KeyError(f"Unknown source: {source}")


def _digest(downloaded):
    digest = hashlib.sha256()
    for name, data in downloaded:
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(data)
    return digest.hexdigest()


def _write_refresh_log(source, status, count, message, retrieved_at, sha256=""):
    with _db_connection() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO refresh_log VALUES(?,?,?,?,?,?)",
            (source, status, count, message, retrieved_at, sha256),
        )


def refresh(source):
    if source not in SOURCES:
        raise KeyError(f"Unknown source: {source}")
    if source == MANUAL_SOURCE:
        raise SourceNotConfigured("UNGM must be checked separately")
    now = datetime.now(timezone.utc).isoformat()
    try:
        records, downloaded = _fetch_source(source)
        if not records:
            raise ValueError("Parser produced zero records")
        with _db_connection() as connection:
            connection.execute("BEGIN")
            connection.execute("DELETE FROM records WHERE source=?", (source,))
            connection.executemany(
                """
                INSERT INTO records(
                    source,source_ref,name,aliases,country,entity_type,programmes,source_url,retrieved_at
                ) VALUES(
                    :source,:source_ref,:name,:aliases,:country,:entity_type,:programmes,:source_url,:retrieved_at
                )
                """,
                [{**record, "retrieved_at": now} for record in records],
            )
            connection.execute(
                "INSERT OR REPLACE INTO refresh_log VALUES(?,?,?,?,?,?)",
                (source, "OK", len(records), "", now, _digest(downloaded)),
            )
        return len(records)
    except SourceNotConfigured as exc:
        with _db_connection() as connection:
            retained = connection.execute(
                "SELECT COUNT(*) FROM records WHERE source=?", (source,)
            ).fetchone()[0]
        _write_refresh_log(source, "NOT_CONFIGURED", retained, str(exc), now)
        raise
    except Exception as exc:
        with _db_connection() as connection:
            retained = connection.execute(
                "SELECT COUNT(*) FROM records WHERE source=?", (source,)
            ).fetchone()[0]
        _write_refresh_log(
            source,
            "ERROR",
            retained,
            f"{type(exc).__name__}: {exc}",
            now,
        )
        raise


if __name__ == "__main__":
    init()
    failed = False
    for source in SOURCES:
        if source == MANUAL_SOURCE:
            continue
        try:
            print(source, refresh(source))
        except SourceNotConfigured as exc:
            print(source, "NOT_CONFIGURED", exc)
        except Exception as exc:
            print(source, "ERROR", exc)
            failed = True
    if failed:
        sys.exit(1)
