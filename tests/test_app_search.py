import os
import re
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import app as sanctions_app
import export_offline_html
import ingest


class CountrySearchTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = os.path.join(self.temp_dir.name, "country-search.db")
        self.app_patch = patch.object(sanctions_app, "DB", self.database)
        self.ingest_patch = patch.object(ingest, "DB", self.database)
        self.app_patch.start()
        self.ingest_patch.start()
        ingest.init()
        with closing(sqlite3.connect(self.database)) as connection:
            with connection:
                connection.executemany(
                    """
                    INSERT INTO records(source,name,country,source_url)
                    VALUES(?,?,?,?)
                    """,
                    [
                        (
                            "OFAC_SDN",
                            "First Person",
                            "United States",
                            "https://example.org",
                        ),
                        (
                            "UK",
                            "Second Person",
                            "Canada | United Kingdom",
                            "https://example.org",
                        ),
                        ("EU", "Third Person", "Tunisia", "https://example.org"),
                        ("OFAC_SDN", "Macau Person", "Macau", "https://example.org"),
                        (
                            "OFAC_SDN",
                            "South Sudan Person",
                            "South Sudan",
                            "https://example.org",
                        ),
                        (
                            "OFAC_SDN",
                            "Vatican Person",
                            "Vatican City",
                            "https://example.org",
                        ),
                        (
                            "OFAC_SDN",
                            "Palestine Person",
                            "State of Palestine",
                            "https://example.org",
                        ),
                        (
                            "OFAC_SDN",
                            "Central African Republic Person",
                            "Central African Republic",
                            "https://example.org",
                        ),
                        ("OFAC_SDN", "Chad Person", "Chad", "https://example.org"),
                        ("OFAC_SDN", "Niger Person", "Niger", "https://example.org"),
                        ("OFAC_SDN", "Nigeria Person", "Nigeria", "https://example.org"),
                        (
                            "OFAC_SDN",
                            "Cote d'Ivoire Person",
                            "Côte d'Ivoire",
                            "https://example.org",
                        ),
                        (
                            "OFAC_SDN",
                            "DRC Variant One",
                            "Congo (Democratic Republic)",
                            "https://example.org",
                        ),
                        (
                            "OFAC_SDN",
                            "DRC Variant Two",
                            "Congo, Democratic Republic of the | Rwanda",
                            "https://example.org",
                        ),
                        (
                            "OFAC_SDN",
                            "DRC Variant Three",
                            "Democratic Republic of the Congo",
                            "https://example.org",
                        ),
                        (
                            "OFAC_SDN",
                            "Republic of the Congo Variant One",
                            "Congo",
                            "https://example.org",
                        ),
                        (
                            "OFAC_SDN",
                            "Republic of the Congo Variant Two",
                            "Congo, Republic of",
                            "https://example.org",
                        ),
                        (
                            "OFAC_SDN",
                            "Republic of the Congo Variant Three",
                            "Congo, Republic of the",
                            "https://example.org",
                        ),
                        (
                            "OFAC_SDN",
                            "Czech Republic Variant",
                            "Czech Republic",
                            "https://example.org",
                        ),
                        ("OFAC_SDN", "Czechia Variant", "Czechia", "https://example.org"),
                        ("OFAC_SDN", "Turkey Variant", "Turkey", "https://example.org"),
                        ("OFAC_SDN", "Turkiye Variant", "Turkiye", "https://example.org"),
                        ("OFAC_SDN", "DPRK Variant", "DPRK", "https://example.org"),
                        (
                            "OFAC_SDN",
                            "Korean Peninsula Variant",
                            "Democratic People's Republic of Korea",
                            "https://example.org",
                        ),
                        (
                            "OFAC_SDN",
                            "Region Variant",
                            "Region: Gaza",
                            "https://example.org",
                        ),
                    ],
                )
        self.client = sanctions_app.app.test_client()

    def tearDown(self):
        self.ingest_patch.stop()
        self.app_patch.stop()
        self.temp_dir.cleanup()

    def test_country_prefix_search_works_without_a_name(self):
        response = self.client.get("/api/search?country=Uni")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {record["name"] for record in response.json["results"]},
            {"First Person", "Second Person"},
        )

    def test_car_and_rca_aliases_find_central_african_republic(self):
        for alias in ("CAR", "RCA"):
            with self.subTest(alias=alias):
                response = self.client.get(
                    "/api/search",
                    query_string={"country": alias},
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    {record["name"] for record in response.json["results"]},
                    {"Central African Republic Person"},
                )

    def test_localized_and_common_country_aliases_find_matching_records(self):
        cases = {
            "Tchad": {"Chad Person"},
            "Estados Unidos": {"First Person"},
            "Royaume-Uni": {"Second Person"},
            "République centrafricaine": {"Central African Republic Person"},
            "República Democrática del Congo": {
                "DRC Variant One",
                "DRC Variant Two",
                "DRC Variant Three",
            },
            "Cote d Ivoire": {"Cote d'Ivoire Person"},
            "USA": {"First Person"},
            "UK": {"Second Person"},
            "Holy See": {"Vatican Person"},
            "Vatican": {"Vatican Person"},
            "OPT": {"Palestine Person"},
            "State of Palestine": {"Palestine Person"},
            "Occupied Palestinian Territories": {"Palestine Person"},
            "Macau": {"Macau Person"},
            "China, Macao Special Administrative Region": {"Macau Person"},
        }

        for alias, expected_names in cases.items():
            with self.subTest(alias=alias):
                response = self.client.get(
                    "/api/search",
                    query_string={"country": alias},
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    {record["name"] for record in response.json["results"]},
                    expected_names,
                )

    def test_every_localized_alias_searches_its_country(self):
        country_records = []
        expected_names = {}
        aliases_by_country = {
            canonical: list(aliases)
            for canonical, aliases in sanctions_app.COUNTRY_LOCALIZED_ALIASES.items()
        }
        for canonical, aliases in sanctions_app.COUNTRY_EXTRA_ALIASES.items():
            canonical_name = sanctions_app.COUNTRY_DISPLAY_NAMES.get(
                sanctions_app.country_alias_key(canonical),
                canonical,
            )
            aliases_by_country.setdefault(canonical_name, []).extend(aliases)

        for index, (canonical, aliases) in enumerate(aliases_by_country.items()):
            if not aliases:
                continue
            name = f"Localized alias coverage {index:03}"
            country = sanctions_app.COUNTRY_SEARCH_VARIANTS.get(
                canonical,
                (canonical,),
            )[0]
            country_records.append(
                ("ALIAS_COVERAGE", name, country, "https://example.org")
            )
            expected_names[canonical] = name

        with closing(sqlite3.connect(self.database)) as connection:
            with connection:
                connection.executemany(
                    """
                    INSERT INTO records(source,name,country,source_url)
                    VALUES(?,?,?,?)
                    """,
                    country_records,
                )

        for canonical, aliases in aliases_by_country.items():
            for alias in aliases:
                with self.subTest(canonical=canonical, alias=alias):
                    response = self.client.get(
                        "/api/search",
                        query_string={
                            "country": alias,
                            "source": "ALIAS_COVERAGE",
                        },
                    )

                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(
                        {record["name"] for record in response.json["results"]},
                        {expected_names[canonical]},
                    )

    def test_exact_country_search_does_not_confuse_prefixes(self):
        for country, expected_name in (
            ("Niger", "Niger Person"),
            ("Nigeria", "Nigeria Person"),
        ):
            with self.subTest(country=country):
                response = self.client.get(
                    "/api/search",
                    query_string={"country": country},
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    {record["name"] for record in response.json["results"]},
                    {expected_name},
                )

    def test_due_diligence_demo_has_a_separate_flask_page_not_static_export(self):
        page = self.client.get("/").get_data(as_text=True)
        certification_page = self.client.get("/certification").get_data(as_text=True)
        static_page = export_offline_html.build_html(
            page,
            [],
            {},
            "test timestamp",
        )

        self.assertIn('href="/certification"', page)
        self.assertNotIn('id="partner-certification"', page)
        self.assertIn('id="partner-certification"', certification_page)
        self.assertIn('id="screen-certification-entities"', certification_page)
        self.assertIn("data-source-sha256=", certification_page)
        self.assertIn('data-i18n="certificationDemoNotice"', certification_page)
        self.assertIn('id="cert-entity-country-options"', certification_page)
        self.assertIn('id="cert-organisation"', certification_page)
        self.assertIn('id="cert-screened-by"', certification_page)
        self.assertIn('id="cert-role"', certification_page)
        self.assertIn('id="cert-user-email"', certification_page)
        self.assertIn('type="email"', certification_page)
        self.assertIn('id="edit-certification-request"', certification_page)
        self.assertIn('id="reset-certification-request"', certification_page)
        self.assertIn('id="reset-certification-entity"', certification_page)
        self.assertIn('id="new-certification-exercise"', certification_page)
        self.assertLess(certification_page.index('id="cert-entity-name"'), certification_page.index('id="cert-fuzzy-matching"'))
        self.assertLess(certification_page.index('id="cert-fuzzy-matching"'), certification_page.index('id="cert-entity-category"'))
        self.assertIn("Start a new Search Report", certification_page)
        self.assertNotIn("CBPF", certification_page)
        self.assertNotIn("cert-project-", certification_page)
        self.assertNotIn("Funding application reference", certification_page)
        self.assertNotIn('id="search-panel"', certification_page)
        self.assertNotIn('id="partner-certification"', static_page)
        self.assertNotIn("/static/certification.js", static_page)
        self.assertNotIn('href="/certification"', static_page)
        self.assertNotIn('id="refresh-all-sources"', static_page)
        self.assertNotIn("fetch(", static_page)
        self.assertIn('id="snapshot-notice"', static_page)

    def test_source_refresh_can_be_disabled_for_public_demonstrations(self):
        with patch.dict(sanctions_app.app.config, {"SOURCE_REFRESH_ENABLED": False}):
            with patch.object(sanctions_app, "refresh") as refresh:
                response = self.client.post("/api/refresh/OFAC_SDN")
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json["error"], "Source refresh is disabled")
            refresh.assert_not_called()
            page = self.client.get("/").get_data(as_text=True)
            self.assertNotIn('class="refresh-button"', page)

        with patch.dict(sanctions_app.app.config, {"SOURCE_REFRESH_ENABLED": True}):
            with patch.object(sanctions_app, "refresh", return_value=2) as refresh:
                response = self.client.post("/api/refresh/OFAC_SDN")
            self.assertEqual(response.status_code, 200)
            refresh.assert_called_once_with("OFAC_SDN")
            page = self.client.get("/").get_data(as_text=True)
            self.assertIn('class="refresh-button"', page)
            self.assertEqual(page.count('id="refresh-all-sources"'), 1)

    def test_ungm_is_visible_but_never_refreshed_or_searched(self):
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute(
                "INSERT INTO records(source,name,country) VALUES(?,?,?)",
                ("UNGM", "Legacy Unique Supplier", "Legacyland"),
            )
        for fuzzy in ("false", "true"):
            response = self.client.get(
                "/api/search",
                query_string={"name": "Legacy Unique Supplier", "fuzzy_match": fuzzy},
            )
            self.assertEqual(response.json["count"], 0)
        self.assertEqual(self.client.get("/api/search?source=UNGM").status_code, 403)
        with patch.dict(sanctions_app.app.config, {"SOURCE_REFRESH_ENABLED": True}):
            with patch.object(sanctions_app, "refresh") as mocked_refresh:
                self.assertEqual(self.client.post("/api/refresh/UNGM").status_code, 403)
                mocked_refresh.assert_not_called()
        page = self.client.get("/").get_data(as_text=True)
        self.assertRegex(page, r'<option value="UNGM"[^>]*disabled')
        self.assertRegex(page, r'data-status="MANUAL" data-source-key="UNGM"')
        self.assertNotIn("Legacyland", page)
        output = Path(self.temp_dir.name) / "snapshot.html"
        export_offline_html.export(output)
        self.assertNotIn("Legacy Unique Supplier", output.read_text(encoding="utf-8"))

    def test_seed_skips_ungm_even_when_it_is_the_only_existing_source(self):
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("DELETE FROM records")
            connection.execute("INSERT INTO records(source,name) VALUES('UNGM','Legacy')")
        with patch.object(sanctions_app, "SOURCES", {"UNGM": "", "EU": ""}):
            with patch.object(sanctions_app, "refresh", return_value=0) as mocked_refresh:
                self.assertEqual(sanctions_app.ensure_seed_data(), 0)
                mocked_refresh.assert_called_once_with("EU")

    def test_seed_reports_when_no_sources_load(self):
        with closing(sqlite3.connect(self.database)) as connection:
            with connection:
                connection.execute("DELETE FROM records")
        with patch.object(sanctions_app, "SOURCES", {"OFAC_SDN": "unused"}):
            with patch.object(sanctions_app, "refresh", side_effect=RuntimeError("failed")):
                with self.assertLogs(sanctions_app.app.logger, level="WARNING"):
                    self.assertEqual(sanctions_app.ensure_seed_data(), 0)

    def test_pages_include_skip_link_branding_and_un_footer(self):
        for path in ("/", "/certification"):
            with self.subTest(path=path):
                page = self.client.get(path).get_data(as_text=True)
                self.assertIn('class="skip-link"', page)
                self.assertIn('href="#main-content"', page)
                self.assertIn('id="main-content"', page)
                self.assertIn('class="un-branding-bar"', page)
                self.assertIn('href="https://www.un.org/"', page)
                self.assertIn('href="https://search.un.org/"', page)
                self.assertIn('class="un-site-footer"', page)
                self.assertIn('footerCopyright', page)
                self.assertIn('footerTerms', page)
                self.assertIn('footerPrivacy', page)
                self.assertIn('footerSiteIndex', page)
                self.assertIn('footerFraudAlert', page)

    def test_fuzzy_search_finds_similar_names_and_exposes_a_heuristic_score(self):
        with closing(sqlite3.connect(self.database)) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO records(source,name,aliases,country,source_url)
                    VALUES(?,?,?,?,?)
                    """,
                    (
                        "OFAC_SDN",
                        "Joseph Kony",
                        "",
                        "Uganda",
                        "https://example.org",
                    ),
                )

        exact_response = self.client.get(
            "/api/search",
            query_string={
                "name": "John Kony",
                "source": "OFAC_SDN",
                "page_size": "all",
            },
        )
        fuzzy_response = self.client.get(
            "/api/search",
            query_string={
                "name": "John Kony",
                "source": "OFAC_SDN",
                "fuzzy_match": "true",
                "page_size": "all",
            },
        )

        self.assertEqual(exact_response.status_code, 200)
        self.assertEqual(exact_response.json["count"], 0)
        self.assertEqual(fuzzy_response.status_code, 200)
        self.assertEqual(
            [result["name"] for result in fuzzy_response.json["results"]],
            ["Joseph Kony"],
        )
        self.assertEqual(fuzzy_response.json["results"][0]["match_type"], "fuzzy")
        self.assertEqual(fuzzy_response.json["results"][0]["match_score"], 80.0)

    def test_fuzzy_search_rejects_invalid_toggle_value(self):
        response = self.client.get(
            "/api/search",
            query_string={"name": "Person", "fuzzy_match": "maybe"},
        )

        self.assertEqual(response.status_code, 400)

    def test_country_filters_name_search_and_appears_in_suggestions(self):
        response = self.client.get("/api/search?name=Person&country=Uni")
        page = self.client.get("/").get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {record["name"] for record in response.json["results"]},
            {"First Person", "Second Person"},
        )
        self.assertIn('data-country="United States of America"', page)
        self.assertIn(
            'data-country="United Kingdom of Great Britain and Northern Ireland"',
            page,
        )
        self.assertIn('data-country="Democratic Republic of the Congo"', page)
        self.assertIn('data-aliases="DRC|RDC"', page)
        self.assertIn('data-aliases="CAR|RCA"', page)
        self.assertIn('data-country="South Sudan"', page)
        self.assertIn('data-country="Holy See"', page)
        self.assertIn('data-aliases="Vatican"', page)
        self.assertIn('data-country="Occupied Palestinian Territories"', page)
        self.assertIn('data-aliases="OPT"', page)
        self.assertIn('data-country="Chad"', page)
        self.assertIn('data-search-aliases="Chad|Tchad"', page)
        self.assertNotIn('data-country="Tchad"', page)
        self.assertIn('id="reset-search"', page)
        self.assertIn('id="pagination"', page)
        self.assertIn('id="page-size"', page)
        self.assertIn('data-language="en"', page)
        self.assertIn('data-language="fr"', page)
        self.assertIn('data-language="es"', page)
        self.assertIn('/static/i18n.js', page)
        congo_options = {
            country
            for country in re.findall(r'data-country="([^"]+)"', page)
            if "congo" in country.casefold()
        }
        self.assertEqual(
            congo_options,
            {"Democratic Republic of the Congo", "Congo"},
        )
        for size in (25, 50, 75, 100):
            self.assertIn(f'<option value="{size}">{size}</option>', page)
        self.assertIn(
            '<option value="all" data-i18n="allResults">All results</option>',
            page,
        )

    def test_drc_and_rdc_search_all_indexed_country_variants(self):
        expected = {"DRC Variant One", "DRC Variant Two", "DRC Variant Three"}

        for alias in ("DRC", "RDC", "Democratic Republic of Congo"):
            with self.subTest(alias=alias):
                response = self.client.get("/api/search", query_string={"country": alias})

                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    {record["name"] for record in response.json["results"]},
                    expected,
                )

    def test_republic_of_the_congo_search_does_not_match_drc_records(self):
        expected = {
            "Republic of the Congo Variant One",
            "Republic of the Congo Variant Two",
            "Republic of the Congo Variant Three",
        }
        for country in ("Republic of the Congo", "Congo"):
            with self.subTest(country=country):
                response = self.client.get(
                    "/api/search",
                    query_string={"country": country},
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    {record["name"] for record in response.json["results"]},
                    expected,
                )

    def test_country_aliases_collapse_to_one_suggestion_and_search_all_variants(self):
        page = self.client.get("/").get_data(as_text=True)
        countries = re.findall(r'data-country="([^"]+)"', page)

        self.assertEqual(countries.count("Czechia"), 1)
        self.assertNotIn("Czech Republic", countries)
        self.assertEqual(countries.count("Türkiye"), 1)
        self.assertNotIn("Turkey", countries)
        self.assertNotIn("Turkiye", countries)
        self.assertNotIn("DPRK", countries)
        self.assertNotIn("Democratic People's Republic of Korea", countries)
        self.assertNotIn("Region: Gaza", countries)

        response = self.client.get(
            "/api/search",
            query_string={"country": "Korea, North"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {record["name"] for record in response.json["results"]},
            {"DPRK Variant", "Korean Peninsula Variant"},
        )

        expected_turkiye = {"Turkey Variant", "Turkiye Variant"}
        for alias in ("Türkiye", "Turkey", "Turkiye"):
            with self.subTest(country=alias):
                response = self.client.get(
                    "/api/search",
                    query_string={"country": alias},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    {record["name"] for record in response.json["results"]},
                    expected_turkiye,
                )

    def test_search_results_support_page_sizes_and_report_the_total(self):
        with closing(sqlite3.connect(self.database)) as connection:
            with connection:
                connection.executemany(
                    """
                    INSERT INTO records(source,name,country,source_url)
                    VALUES(?,?,?,?)
                    """,
                    [
                        (
                            "OFAC_SDN",
                            f"Pagination Match {index:02}",
                            "Pagination Testland",
                            "https://example.org",
                        )
                        for index in range(127)
                    ],
                )

        first_page = self.client.get("/api/search?country=Pag&page=1")
        second_page = self.client.get("/api/search?country=Pag&page=2")
        last_page = self.client.get("/api/search?country=Pag&page=6")
        all_results = self.client.get(
            "/api/search?country=Pag&page_size=all"
        )

        self.assertEqual(first_page.status_code, 200)
        self.assertEqual(first_page.json["count"], 127)
        self.assertEqual(first_page.json["page_size"], 25)
        self.assertEqual(first_page.json["total_pages"], 6)
        self.assertTrue(first_page.json["has_next"])
        self.assertFalse(first_page.json["has_previous"])
        self.assertEqual(len(first_page.json["results"]), 25)

        self.assertEqual(second_page.status_code, 200)
        self.assertEqual(second_page.json["page"], 2)
        self.assertTrue(second_page.json["has_previous"])
        self.assertTrue(second_page.json["has_next"])
        self.assertEqual(len(second_page.json["results"]), 25)
        first_page_names = {record["name"] for record in first_page.json["results"]}
        second_page_names = {record["name"] for record in second_page.json["results"]}
        self.assertEqual(len(first_page_names | second_page_names), 50)
        self.assertTrue(first_page_names.isdisjoint(second_page_names))
        self.assertEqual(last_page.status_code, 200)
        self.assertEqual(last_page.json["page"], 6)
        self.assertFalse(last_page.json["has_next"])
        self.assertEqual(len(last_page.json["results"]), 2)

        for size in (25, 50, 75, 100):
            with self.subTest(page_size=size):
                response = self.client.get(
                    "/api/search",
                    query_string={"country": "Pag", "page_size": size},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json["page_size"], size)
                self.assertEqual(response.json["total_pages"], (127 + size - 1) // size)
                self.assertEqual(len(response.json["results"]), size)

        self.assertEqual(all_results.status_code, 200)
        self.assertEqual(all_results.json["page"], 1)
        self.assertEqual(all_results.json["page_size"], 127)
        self.assertEqual(all_results.json["total_pages"], 1)
        self.assertFalse(all_results.json["has_next"])
        self.assertEqual(len(all_results.json["results"]), 127)

        invalid_page = self.client.get("/api/search?country=Pag&page=0")
        self.assertEqual(invalid_page.status_code, 400)
        invalid_page_size = self.client.get(
            "/api/search?country=Pag&page_size=30"
        )
        self.assertEqual(invalid_page_size.status_code, 400)


if __name__ == "__main__":
    unittest.main()
