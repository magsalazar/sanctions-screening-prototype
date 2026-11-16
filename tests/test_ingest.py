import csv
import io
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import ingest


class IngestParserTests(unittest.TestCase):
    def test_unsc_parses_individual_names_aliases_and_country(self):
        data = b"""<CONSOLIDATED_LIST><INDIVIDUALS_LIST><INDIVIDUAL>
        <REFERENCE_NUMBER>QDi.1</REFERENCE_NUMBER><FIRST_NAME>Test Person</FIRST_NAME>
        <UN_LIST_TYPE>Al-Qaida</UN_LIST_TYPE><INDIVIDUAL_ALIAS><ALIAS_NAME>Alias Person</ALIAS_NAME></INDIVIDUAL_ALIAS>
        <INDIVIDUAL_ADDRESS><COUNTRY>Exampleland</COUNTRY></INDIVIDUAL_ADDRESS>
        </INDIVIDUAL></INDIVIDUALS_LIST></CONSOLIDATED_LIST>"""

        result = ingest.unsc(data)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Test Person")
        self.assertEqual(result[0]["aliases"], "Alias Person")
        self.assertEqual(result[0]["country"], "Exampleland")

    def test_ofac_bundle_joins_alias_and_address_rows(self):
        result = ingest.ofac_bundle(
            b'1,"Primary Name",entity,PROGRAM\n',
            b'1,2,aka,"Alternate Name",-0-\n',
            b'1,3,Street,City,Exampleland,-0-\n',
            "OFAC_SDN",
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["aliases"], "Alternate Name")
        self.assertEqual(result[0]["country"], "Exampleland")

    def test_eu_csv_groups_multiple_names_under_entity(self):
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "Entity_LogicalId",
                "Entity_EU_ReferenceNumber",
                "Entity_SubjectType_ClassificationCode",
                "Entity_Regulation_Programme",
                "NameAlias_WholeName",
                "Address_CountryDescription",
            ],
            delimiter=";",
        )
        writer.writeheader()
        writer.writerows(
            [
                {
                    "Entity_LogicalId": "10",
                    "Entity_EU_ReferenceNumber": "EU.1",
                    "Entity_SubjectType_ClassificationCode": "person",
                    "Entity_Regulation_Programme": "TEST",
                    "NameAlias_WholeName": "Primary Person",
                    "Address_CountryDescription": "Exampleland",
                },
                {
                    "Entity_LogicalId": "10",
                    "Entity_EU_ReferenceNumber": "EU.1",
                    "Entity_SubjectType_ClassificationCode": "person",
                    "Entity_Regulation_Programme": "TEST",
                    "NameAlias_WholeName": "Alias Person",
                    "Address_CountryDescription": "",
                },
            ]
        )

        result = ingest.eu(output.getvalue().encode("utf-8"))

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Primary Person")
        self.assertEqual(result[0]["aliases"], "Alias Person")
        self.assertEqual(result[0]["country"], "Exampleland")

    def test_uk_csv_skips_preamble_and_groups_name_variants(self):
        data = (
            b"Report Date: 01-Jan-2026\r\n"
            b"Unique ID,Name 6,Name type,Address Country,Regime Name\r\n"
            b"UK123,Primary Person,Individual,Exampleland,Test Regime\r\n"
            b"UK123,Alias Person,Individual,Exampleland,Test Regime\r\n"
        )

        result = ingest.uk(data)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Primary Person")
        self.assertEqual(result[0]["aliases"], "Alias Person")
        self.assertEqual(result[0]["country"], "Exampleland")

    def test_world_bank_includes_debarred_and_cross_debarred_only(self):
        result = ingest.world_bank(
            b"""{"response":{"ZPROCSUPP":[
            {"SUPP_ID":1,"SUPP_NAME":"Debarred Firm","SUPP_TYPE_CODE":"F","INELIG_FLG":"D","SUPP_ELIG_STAT":"DEBARRED"},
            {"SUPP_ID":2,"SUPP_NAME":"Cross Debarred Firm","SUPP_TYPE_CODE":"F","INELIG_FLG":"X","SUPP_ELIG_STAT":"X-DEBARRED"},
            {"SUPP_ID":3,"SUPP_NAME":"Other Sanction","INELIG_FLG":"O","SUPP_ELIG_STAT":"OTHER"}
            ]}}"""
        )

        self.assertEqual([record["name"] for record in result], ["Debarred Firm", "Cross Debarred Firm"])

    def test_ungm_json_maps_common_supplier_fields(self):
        result = ingest.ungm(
            b'{"data":[{"supplier_name":"Example Supplier","supplier_id":"42","country":"Exampleland"}]}'
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Example Supplier")
        self.assertEqual(result[0]["source_ref"], "42")
        self.assertEqual(result[0]["country"], "Exampleland")

    def test_failed_refresh_keeps_last_successful_records(self):
        with tempfile.TemporaryDirectory() as directory:
            database = os.path.join(directory, "test.db")
            with patch.object(ingest, "DB", database):
                ingest.init()
                with sqlite3.connect(database) as connection:
                    connection.execute(
                        "INSERT INTO records(source,name) VALUES(?,?)",
                        ("EU", "Existing record"),
                    )
                connection.close()
                with patch.object(ingest, "_fetch_source", side_effect=RuntimeError("feed unavailable")):
                    with self.assertRaisesRegex(RuntimeError, "feed unavailable"):
                        ingest.refresh("EU")
                with sqlite3.connect(database) as connection:
                    self.assertEqual(
                        connection.execute("SELECT COUNT(*) FROM records WHERE source='EU'").fetchone()[0],
                        1,
                    )
                    self.assertEqual(
                        connection.execute("SELECT status,count FROM refresh_log WHERE source='EU'").fetchone(),
                        ("ERROR", 1),
                    )
                connection.close()


if __name__ == "__main__":
    unittest.main()
