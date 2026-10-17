import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import sparsity_interaction as si


class SparsityInteractionTests(unittest.TestCase):
    def test_fixed_prior_difficulty_bands(self):
        self.assertEqual(si.difficulty_band(0), "within_5pp")
        self.assertEqual(si.difficulty_band(-5), "within_5pp")
        self.assertEqual(si.difficulty_band(5.01), "five_to_10pp")
        self.assertEqual(si.difficulty_band(-10), "five_to_10pp")
        self.assertEqual(si.difficulty_band(10.01), "ten_to_20pp")
        self.assertEqual(si.difficulty_band(-20), "ten_to_20pp")
        self.assertEqual(si.difficulty_band(20.01), "over_20pp")
        self.assertEqual(si.COMPETITIVE_PRIOR_THRESHOLD_PP, 10.0)

    def test_fixed_regions(self):
        self.assertEqual(si.region_for_race_code("NY-04"), "Northeast")
        self.assertEqual(si.region_for_race_code("MI-07"), "Midwest")
        self.assertEqual(si.region_for_race_code("TX-15"), "South")
        self.assertEqual(si.region_for_race_code("CA-13"), "West")
        self.assertEqual(si.region_for_race_code("ZZ-01"), "Unknown")

    def test_interaction_cells_are_predefined(self):
        rows = [
            {
                "prior_competitive_10pp": True,
                "poll_sparse": True,
                "source_sparse": True,
                "prior_abs_margin_pp": 4.0,
                "raw_poll_margin_d_minus_r": 3.0,
                "prior_margin_d_minus_r": 4.0,
                "full_model_margin_d_minus_r": 3.5,
                "result_margin_d_minus_r": 1.0,
            },
            {
                "prior_competitive_10pp": True,
                "poll_sparse": False,
                "source_sparse": False,
                "prior_abs_margin_pp": 7.0,
                "raw_poll_margin_d_minus_r": 1.0,
                "prior_margin_d_minus_r": 7.0,
                "full_model_margin_d_minus_r": 2.0,
                "result_margin_d_minus_r": 0.0,
            },
            {
                "prior_competitive_10pp": False,
                "poll_sparse": True,
                "source_sparse": True,
                "prior_abs_margin_pp": 15.0,
                "raw_poll_margin_d_minus_r": 12.0,
                "prior_margin_d_minus_r": 15.0,
                "full_model_margin_d_minus_r": 13.0,
                "result_margin_d_minus_r": 10.0,
            },
        ]
        cells = si.interaction_cells(rows, "poll_sparse")
        self.assertEqual(len(cells), 4)
        keyed = {(c["prior_competitiveness"], c["sparsity"]): c for c in cells}
        self.assertEqual(keyed[("within_10pp", "sparse")]["n"], 1)
        self.assertEqual(keyed[("within_10pp", "multi")]["n"], 1)
        self.assertEqual(keyed[("over_10pp", "sparse")]["n"], 1)
        self.assertEqual(keyed[("over_10pp", "multi")]["state"], "unavailable")

    def test_geography_summary_does_not_define_regions_from_outcomes(self):
        rows = [{
            "region": "West",
            "prior_competitive_10pp": True,
            "poll_sparse": True,
            "source_sparse": True,
            "prior_abs_margin_pp": 3.0,
            "raw_poll_margin_d_minus_r": 2.0,
            "prior_margin_d_minus_r": 3.0,
            "full_model_margin_d_minus_r": 2.5,
            "result_margin_d_minus_r": -1.0,
        }]
        summary = si.geography_rows(rows)
        west = next(r for r in summary if r["region"] == "West")
        self.assertEqual(west["n"], 1)
        self.assertEqual(west["competitive_prior_n"], 1)
        self.assertEqual(west["one_poll_n"], 1)
        self.assertEqual(west["one_pollster_n"], 1)


if __name__ == "__main__":
    unittest.main()
