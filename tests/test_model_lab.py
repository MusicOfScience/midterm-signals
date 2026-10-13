import importlib.util
import math
from datetime import date
from pathlib import Path
import unittest

P = Path(__file__).resolve().parents[1] / "scripts" / "model_lab.py"
spec = importlib.util.spec_from_file_location("model_lab", P)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ModelLabTests(unittest.TestCase):
    def test_production_contract_is_still_frozen(self):
        state = m.production_contract_state()
        self.assertEqual(state["state"], "verified", state.get("missing_markers"))
        self.assertFalse(state["blocking"])

    def test_available_date_uses_publication_date(self):
        row = {"end_date": "2022-10-01", "publication_date": "2022-10-05"}
        self.assertEqual(m.available_date(row), date(2022, 10, 5))
        self.assertEqual(m.rows_known_by([row], date(2022, 10, 4)), [])
        self.assertEqual(len(m.rows_known_by([row], date(2022, 10, 5))), 1)

    def test_race_roster_is_as_of_not_final(self):
        rows = [
            {"race_code": "XX-01", "known_date": "2022-08-01", "dem_name": "Alpha"},
            {"race_code": "XX-01", "known_date": "2022-10-20", "dem_name": "Beta"},
        ]
        early = m.select_race_versions(rows, date(2022, 9, 1))
        late = m.select_race_versions(rows, date(2022, 10, 25))
        self.assertEqual(early[0]["dem_name"], "Alpha")
        self.assertEqual(late[0]["dem_name"], "Beta")

    def test_brier_known_vector(self):
        p = [0.9, 0.8, 0.2, 0.1]
        y = [1, 1, 0, 0]
        self.assertAlmostEqual(m.brier_score(p, y), 0.025, places=12)

    def test_log_loss_known_vector(self):
        p = [0.8, 0.2]
        y = [1, 0]
        self.assertAlmostEqual(m.log_loss(p, y), -math.log(0.8), places=12)

    def test_incomplete_results_refuse_score(self):
        preds = [
            {"race_code": "A", "dem_probability": 0.7, "rep_probability": 0.3},
            {"race_code": "B", "dem_probability": 0.4, "rep_probability": 0.6},
        ]
        score = m.score_checkpoint(preds, {"A": 1})
        self.assertEqual(score["state"], "unscored")
        self.assertEqual(score["missing_outcomes"], ["B"])

    def test_calibration_bins_preserve_counts(self):
        p = [0.05, 0.15, 0.51, 0.55, 0.94]
        y = [0, 0, 1, 0, 1]
        bins = m.calibration_bins(p, y)
        self.assertEqual(sum(b["count"] for b in bins), len(p))

    def test_replay_probability_does_not_accept_results(self):
        self.assertNotIn("results", m.race_probability.__code__.co_varnames[:m.race_probability.__code__.co_argcount])


if __name__ == "__main__":
    unittest.main()
