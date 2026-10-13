import importlib.util
from pathlib import Path
import unittest

P = Path(__file__).resolve().parents[1] / "scripts" / "baseline_stability.py"
spec = importlib.util.spec_from_file_location("baseline_stability", P)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class BaselineStabilityTests(unittest.TestCase):
    def test_fixed_band_boundaries(self):
        self.assertEqual(m.stability_band(0), "stable_0_5")
        self.assertEqual(m.stability_band(5), "stable_0_5")
        self.assertEqual(m.stability_band(5.0001), "moderate_5_10")
        self.assertEqual(m.stability_band(10), "moderate_5_10")
        self.assertEqual(m.stability_band(10.0001), "high_10_15")
        self.assertEqual(m.stability_band(15), "high_10_15")
        self.assertEqual(m.stability_band(15.0001), "very_high_gt_15")

    def test_profile_uses_relative_not_raw_presidential_margins(self):
        row = {
            "race_code": "XX-01",
            "margin_earliest": "8",
            "margin_middle": "4",
            "margin_latest": "0",
        }
        national = {"earliest": 6, "middle": 2, "latest": -2}
        profile = m.structural_profile(row, national)
        self.assertEqual(profile["relative_leans_d_minus_r"], [2.0, 2.0, 2.0])
        self.assertEqual(profile["range_pp"], 0.0)
        self.assertEqual(profile["trend_earliest_to_latest_pp"], 0.0)
        self.assertEqual(profile["band"], "stable_0_5")

    def test_profile_assignment_does_not_accept_outcomes(self):
        row = {
            "race_code": "XX-01",
            "margin_earliest": "-8",
            "margin_middle": "0",
            "margin_latest": "9",
        }
        national = {"earliest": 0, "middle": 0, "latest": 0}
        profile = m.structural_profile(row, national)
        self.assertEqual(profile["range_pp"], 17.0)
        self.assertEqual(profile["band"], "very_high_gt_15")
        with self.assertRaises(TypeError):
            m.structural_profile(row, national, {"XX-01": 1})

    def test_checkpoint_scores_preassigned_bands(self):
        structural_rows = {
            "A": {"race_code": "A", "margin_earliest": "0", "margin_middle": "1", "margin_latest": "2"},
            "B": {"race_code": "B", "margin_earliest": "-12", "margin_middle": "0", "margin_latest": "8"},
        }
        national = {"earliest": 0, "middle": 0, "latest": 0}
        checkpoint = {
            "generic_ballot_margin_d_minus_r": 2.0,
            "predictions": [
                {
                    "race_code": "A", "race_type": "house", "dem_candidate": "D A", "rep_candidate": "R A",
                    "prior_margin": 2.0, "dem_probability": 0.75, "poll_count": 2,
                },
                {
                    "race_code": "B", "race_type": "house", "dem_candidate": "D B", "rep_candidate": "R B",
                    "prior_margin": 2.0, "dem_probability": 0.25, "poll_count": 1,
                },
            ],
        }
        result = m.checkpoint_stability(checkpoint, {"A": 1, "B": 0}, structural_rows, national)
        self.assertEqual(result["state"], "scored")
        self.assertEqual(result["n"], 2)
        self.assertFalse(result["band_assignment_uses_outcomes"])
        counts = {row["band"]: row["n"] for row in result["bands"]}
        self.assertEqual(counts["stable_0_5"], 1)
        self.assertEqual(counts["very_high_gt_15"], 1)
        self.assertEqual(result["high_instability_n"], 1)

    def test_no_opponent_race_is_excluded(self):
        checkpoint = {
            "generic_ballot_margin_d_minus_r": 0,
            "predictions": [
                {
                    "race_code": "A", "race_type": "house", "dem_candidate": "D", "rep_candidate": None,
                    "prior_margin": 0, "dem_probability": .999, "poll_count": 0,
                }
            ],
        }
        rows = {"A": {"race_code": "A", "margin_earliest": "0", "margin_middle": "0", "margin_latest": "0"}}
        result = m.checkpoint_stability(checkpoint, {"A": 1}, rows, {"earliest": 0, "middle": 0, "latest": 0})
        self.assertEqual(result["state"], "unavailable")
        self.assertEqual(result["n"], 0)


if __name__ == "__main__":
    unittest.main()
