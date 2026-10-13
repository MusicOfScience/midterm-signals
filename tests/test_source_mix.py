import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import source_mix as sm


class SourceMixTests(unittest.TestCase):
    def test_fixed_band_contract(self):
        self.assertEqual(sm.band_for(1, sm.DEPTH_BANDS), "one_poll")
        self.assertEqual(sm.band_for(2, sm.DEPTH_BANDS), "two_polls")
        self.assertEqual(sm.band_for(3, sm.DEPTH_BANDS), "three_four_polls")
        self.assertEqual(sm.band_for(4, sm.DEPTH_BANDS), "three_four_polls")
        self.assertEqual(sm.band_for(5, sm.DEPTH_BANDS), "five_plus_polls")
        self.assertAlmostEqual(sm.TOP_SOURCE_CONCENTRATION_THRESHOLD, 2 / 3)
        self.assertEqual(sm.POLLSTER_MIN_RACE_SOURCES, 5)

    def test_source_profile_uses_poll_metadata_only(self):
        race = {
            "race_code": "ZZ-01", "race_type": "house", "known_date": "2022-01-01",
            "dem_name": "Alice Democrat", "rep_name": "Bob Republican",
        }
        polls = [
            {
                "kind": "race_poll", "race_code": "ZZ-01", "publication_date": "2022-10-01",
                "end_date": "2022-10-01", "pollster": "Alpha", "rating": "2.0", "n": "1000",
                "lean": "D", "dem_name": "Democrat", "rep_name": "Republican", "margin": "4.0",
            },
            {
                "kind": "race_poll", "race_code": "ZZ-01", "publication_date": "2022-10-02",
                "end_date": "2022-10-02", "pollster": "Beta", "rating": "2.0", "n": "1000",
                "lean": "", "dem_name": "Democrat", "rep_name": "Republican", "margin": "0.0",
            },
        ]
        cutoff = date(2022, 10, 2)
        # Derive the frozen values from the same production functions rather than hand-waving them.
        import model_lab as core
        raw, blend, count, latest = core.race_poll_average(polls, race, cutoff)
        pred = {
            "race_code": "ZZ-01", "race_type": "house",
            "dem_candidate": "Alice Democrat", "rep_candidate": "Bob Republican",
            "poll_count": count, "poll_weight": round(blend, 5), "latest_race_poll": latest,
            "prior_margin": 1.0,
            "forecast_margin_d_minus_r": (1 - blend) * 1.0 + blend * raw,
        }
        profile = sm.source_profile(pred, race, polls, cutoff)
        self.assertEqual(profile["poll_count"], 2)
        self.assertEqual(profile["unique_pollsters"], 2)
        self.assertEqual(profile["poll_depth_band"], "two_polls")
        self.assertEqual(profile["source_count_band"], "two_pollsters")
        self.assertEqual(len(profile["source_signals"]), 2)
        self.assertGreater(profile["partisan_labeled_weight_share"], 0)
        self.assertLess(profile["partisan_labeled_weight_share"], 1)
        self.assertEqual(profile["sponsor_band"], "mixed_partisan_labeled")
        self.assertNotIn("result_margin_d_minus_r", profile)
        self.assertNotIn("winner", profile)

    def test_missing_result_margin_is_not_zero(self):
        race = {
            "race_code": "ZZ-01", "race_type": "house", "known_date": "2022-01-01",
            "dem_name": "Alice Democrat", "rep_name": "Bob Republican",
        }
        polls = [{
            "kind": "race_poll", "race_code": "ZZ-01", "publication_date": "2022-10-01",
            "end_date": "2022-10-01", "pollster": "Alpha", "rating": "2.0", "n": "1000",
            "lean": "", "dem_name": "Democrat", "rep_name": "Republican", "margin": "3.0",
        }]
        cutoff = date(2022, 10, 2)
        import model_lab as core
        raw, blend, count, latest = core.race_poll_average(polls, race, cutoff)
        checkpoint = {
            "cutoff": cutoff.isoformat(),
            "predictions": [{
                "race_code": "ZZ-01", "race_type": "house",
                "dem_candidate": "Alice Democrat", "rep_candidate": "Bob Republican",
                "poll_count": count, "poll_weight": round(blend, 5), "latest_race_poll": latest,
                "prior_margin": 1.0,
                "forecast_margin_d_minus_r": (1 - blend) * 1.0 + blend * raw,
            }],
        }
        diag = sm.checkpoint_source_mix(checkpoint, [race], polls, {})
        self.assertEqual(diag["state"], "unavailable")
        self.assertEqual(diag["missing_result_margin_races"], ["ZZ-01"])

    def test_pollster_table_fixed_minimum_and_non_error_ordering(self):
        rows = []
        for i in range(6):
            rows.append({
                "race_code": f"ZZ-{i+1:02d}",
                "result_margin_d_minus_r": 0.0,
                "source_signals": [
                    {"pollster": "Alpha", "margin_d_minus_r": float(i), "weight_share": 0.7, "mean_rating": 2.0, "partisan_labeled_weight_share": 0.0},
                    {"pollster": "Beta", "margin_d_minus_r": 20.0, "weight_share": 0.3, "mean_rating": 1.0, "partisan_labeled_weight_share": 1.0},
                ] if i < 4 else [
                    {"pollster": "Alpha", "margin_d_minus_r": float(i), "weight_share": 1.0, "mean_rating": 2.0, "partisan_labeled_weight_share": 0.0},
                ],
            })
        table = sm.pollster_table(rows)
        self.assertEqual(table["minimum_distinct_race_sources"], 5)
        self.assertEqual(table["reported_pollster_count"], 1)
        self.assertEqual(table["reported_pollsters"][0]["pollster"], "Alpha")
        self.assertIn("never ranked by error", table["ordering"])


if __name__ == "__main__":
    unittest.main()
