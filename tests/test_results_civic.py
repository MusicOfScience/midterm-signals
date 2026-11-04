"""Safety tests for civicAPI national-election ingest, grain, calls, and freshness."""
import unittest
from scripts.refresh_results_civic import (
    consolidate, iso_date, normalise_office, party, race_key,
)


def cand(name, party_code, votes, winner=False):
    return {"name": name, "party": party_code, "votes": votes, "winner": winner}


def sample_house(updated="2026-11-04T08:00:00Z"):
    return {
        "year": 2026, "last_updated": updated, "test_data": False,
        "region_results": {
            "pa-07": {
                "percent_reporting": 96.0,
                "candidates": [
                    cand("Grace Smith", "Democratic", 125000, True),
                    cand("Ron Jones", "Republican", 119000),
                    cand("Libby Green", "Green", 1700),
                ],
            },
            "ak-00": {
                "percent_reporting": 60,
                "candidates": [cand("A", "Democratic", 100), cand("B", "Republican", 70)],
            },
            "oh-08": {
                "candidates": [cand("Zero A", "Democratic", 0), cand("Zero B", "Republican", 0)]
            },
        },
    }


def sample_senate(updated="2026-11-04T08:20:00Z"):
    return {
        "year": "2026", "last_updated": updated,
        "region_results": {
            "ga": {
                "percent_reporting": 95,
                "candidates": [cand("S D", "Democratic Party", 4500000),
                               cand("S R", "Republican", 4000000)],
            },
            "fl-special": {
                "candidates": [cand("F D", "Democratic", 2500000),
                               cand("F R", "Republican", 3100000, True)],
            },
        },
    }


class CivicTests(unittest.TestCase):
    def test_date_parsing_and_2026_scope(self):
        self.assertIsNone(iso_date("2024-11-04T09:00:00Z"))
        self.assertIsNone(iso_date("2026-11-04 09:00"))
        self.assertEqual(iso_date("2026-11-04T08:00:00Z"), "2026-11-04T08:00:00Z")
        self.assertEqual(party("Democratic Party"), "D")
        self.assertEqual(party("Republican"), "R")
        self.assertEqual(party("Independent"), "I")
        self.assertEqual(race_key("AK-00", "house")[0], "AK-01")
        self.assertIsNone(race_key("GU-AL", "senate"))

    def test_house_normalisation_and_named_call(self):
        rows = normalise_office(sample_house(), "house")
        self.assertEqual(len(rows), 3)
        house = next(r for r in rows if r["model_code"] == "PA-07")
        self.assertEqual(house["votes_total"], 245700)
        self.assertEqual(house["leader"]["name"], "Grace Smith")
        self.assertTrue(house["called"])
        self.assertEqual(house["called_by"], "civicAPI decision desk")
        self.assertEqual(house["reporting_unit_pct"], 96.0)
        zero = next(r for r in rows if r["model_code"] == "OH-08")
        self.assertEqual(zero["votes_total"], 0)
        self.assertFalse(zero["called"])

    def test_real_senate_special_keys(self):
        rows = normalise_office(sample_senate(), "senate")
        self.assertEqual(len(rows), 2)
        fl = next(r for r in rows if r["model_code"] == "FL-SEN")
        self.assertTrue(fl["called"])
        self.assertEqual(fl["winner"]["party"], "R")

    def test_missing_2026_date_or_test_data_is_rejected(self):
        doc = sample_house()
        doc["test_data"] = True
        with self.assertRaises(ValueError):
            normalise_office(doc, "house")
        doc = sample_house()
        doc["election_date"] = "2024-11-05"
        with self.assertRaises(ValueError):
            normalise_office(doc, "house")

    def test_partial_house_and_senate_are_not_faked(self):
        results = consolidate({"house": sample_house(), "senate": sample_senate()}, fetched_at="checked")
        reported = [r for r in results["races"] if r["votes_total"] > 0]
        self.assertEqual(len(reported), 4)
        self.assertEqual(results["source_updated_at"], "2026-11-04T08:20:00Z")
        self.assertEqual(results["source"], "civicAPI")
        self.assertTrue(all(r["source_url"].startswith("https://civicapi.org/") for r in reported))
        self.assertEqual(results["ambiguous_keys"], [])

    def test_never_combine_two_senate_contests_into_one_model_seat(self):
        s = sample_senate()
        s["region_results"]["fl"] = {
            "candidates": [cand("Another D", "Democratic", 500000),
                           cand("Another R", "Republican", 700000)]
        }
        result = consolidate({"senate": s})
        self.assertIn("FL-SEN", result["ambiguous_keys"])
        self.assertNotIn("FL-SEN", [r["model_code"] for r in result["races"]])

    def test_regressive_and_failed_sources_do_not_erase_last_good(self):
        prior = consolidate({"house": sample_house(), "senate": sample_senate()}, fetched_at="past")
        older = sample_house("2026-11-04T06:00:00Z")
        older["region_results"]["pa-07"]["candidates"][0]["votes"] = 1
        current = consolidate({"house": older}, prior, fetched_at="later")
        by = {r["model_code"]: r for r in current["races"]}
        self.assertEqual(by["PA-07"]["votes_total"], 245700)
        self.assertEqual(by["GA-SEN"]["votes_total"], 8500000)
        self.assertEqual(current["fetched_at"], "later")

    def test_bad_vote_shape_does_not_invent_count(self):
        doc = sample_house()
        doc["region_results"]["pa-07"]["candidates"][0]["votes"] = "999999"
        doc["region_results"]["pa-07"]["candidates"][1]["votes"] = -5
        results = normalise_office(doc, "house")
        pa = next(r for r in results if r["model_code"] == "PA-07")
        self.assertEqual(pa["votes_total"], 1700)
        self.assertFalse(pa["called"])


if __name__ == "__main__":
    unittest.main()
