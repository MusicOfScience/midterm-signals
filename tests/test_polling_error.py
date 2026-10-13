import csv
import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import polling_error as pe


class PollingErrorTests(unittest.TestCase):
    def test_error_metrics_direction_and_mae(self):
        rows = [
            {"raw_poll_margin_d_minus_r": 4.0, "result_margin_d_minus_r": 1.0},
            {"raw_poll_margin_d_minus_r": -5.0, "result_margin_d_minus_r": -1.0},
        ]
        m = pe.error_metrics(rows, "raw_poll_margin_d_minus_r")
        self.assertEqual(m["n"], 2)
        self.assertAlmostEqual(m["mean_error_d_minus_r_pp"], -0.5)
        self.assertAlmostEqual(m["mae_pp"], 3.5)
        self.assertEqual(m["too_democratic_n"], 1)
        self.assertEqual(m["too_republican_n"], 1)
        self.assertEqual(m["winner_call_accuracy"], 1.0)

    def test_checkpoint_reconstructs_exact_frozen_poll_aggregate(self):
        races = [{
            "race_code": "ZZ-01", "race_type": "house", "known_date": "2022-01-01",
            "dem_name": "Alice Democrat", "rep_name": "Bob Republican",
        }]
        polls = [{
            "kind": "race", "race_code": "ZZ-01", "publication_date": "2022-10-01",
            "end_date": "2022-10-01", "dem_name": "Democrat", "rep_name": "Republican",
            "margin": "3.0", "dem": "51.5", "rep": "48.5", "rating": "1.5", "n": "1000", "lean": "",
        }]
        checkpoint = {
            "cutoff": "2022-10-02",
            "predictions": [{
                "race_code": "ZZ-01", "race_type": "house",
                "dem_candidate": "Alice Democrat", "rep_candidate": "Bob Republican",
                "poll_count": 1, "poll_weight": 0.2, "latest_race_poll": "2022-10-01",
                "prior_margin": 1.0, "forecast_margin_d_minus_r": 1.4,
            }],
        }
        diag = pe.checkpoint_polling_error(checkpoint, races, polls, {"ZZ-01": 2.0})
        self.assertEqual(diag["state"], "scored")
        self.assertEqual(diag["n"], 1)
        house = diag["house_only"]
        self.assertAlmostEqual(house["raw_race_poll_aggregate"]["mean_error_d_minus_r_pp"], 1.0)
        self.assertAlmostEqual(house["published_full_model_margin"]["mae_pp"], 0.6)
        self.assertLess(house["model_comparison"]["mae_delta_full_minus_raw_poll_pp"], 0)

    def test_missing_certified_margin_is_unavailable_not_zero(self):
        races = [{
            "race_code": "ZZ-01", "race_type": "house", "known_date": "2022-01-01",
            "dem_name": "Alice Democrat", "rep_name": "Bob Republican",
        }]
        polls = [{
            "kind": "race", "race_code": "ZZ-01", "publication_date": "2022-10-01",
            "end_date": "2022-10-01", "dem_name": "Democrat", "rep_name": "Republican",
            "margin": "3.0", "rating": "1.5", "n": "1000", "lean": "",
        }]
        checkpoint = {
            "cutoff": "2022-10-02",
            "predictions": [{
                "race_code": "ZZ-01", "race_type": "house",
                "dem_candidate": "Alice Democrat", "rep_candidate": "Bob Republican",
                "poll_count": 1, "poll_weight": 0.2, "latest_race_poll": "2022-10-01",
                "prior_margin": 1.0, "forecast_margin_d_minus_r": 1.4,
            }],
        }
        diag = pe.checkpoint_polling_error(checkpoint, races, polls, {})
        self.assertEqual(diag["state"], "unavailable")
        self.assertEqual(diag["missing_result_margin_races"], ["ZZ-01"])

    def test_checked_in_result_margin_contract(self):
        manifest = json.loads((ROOT / "historical" / "result-margin-provenance.json").read_text())
        self.assertTrue(manifest["evaluation_only"])
        self.assertEqual(manifest["model_effect"], "NONE")
        with (ROOT / "historical" / "2018" / "result-margins.csv").open(newline="") as fh:
            r18 = list(csv.DictReader(fh))
        with (ROOT / "historical" / "2022" / "result-margins.csv").open(newline="") as fh:
            r22 = list(csv.DictReader(fh))
        unavailable = manifest["cycles"]["2022"]["sources"][0]["margin_unavailable"]
        self.assertEqual(len(r18), 470)
        self.assertEqual(len(r22) + len(unavailable), 435)
        self.assertTrue(all(float(r["dem_votes"]) > 0 and float(r["rep_votes"]) > 0 for r in r22))


if __name__ == "__main__":
    unittest.main()
