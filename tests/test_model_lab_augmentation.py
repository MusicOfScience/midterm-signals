import importlib.util
from pathlib import Path
import unittest

P = Path(__file__).resolve().parents[1] / "scripts" / "augment_model_lab.py"
spec = importlib.util.spec_from_file_location("augment_model_lab", P)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ModelLabAugmentationTests(unittest.TestCase):
    def test_prior_probability_uses_frozen_unpolled_sigma(self):
        house = {"race_type": "house", "prior_margin": 0.0}
        senate = {"race_type": "senate", "prior_margin": 0.0}
        self.assertAlmostEqual(m.prior_probability(house), 0.5)
        self.assertAlmostEqual(m.prior_probability(senate), 0.5)

    def test_structural_decomposition_reconstructs_pre_generic_stage(self):
        preds = [{
            "race_code": "A",
            "race_type": "house",
            "dem_candidate": "Dem Candidate",
            "rep_candidate": "Rep Candidate",
            "prior_margin": 2.0,
            "dem_probability": 0.8,
            "poll_count": 2,
        }]
        score = m.structural_decomposition(preds, {"A": 1}, 4.0)
        self.assertEqual(score["state"], "scored")
        self.assertEqual(score["n"], 1)
        structural_p = m.margin_probability(-2.0, "house")
        prior_p = m.margin_probability(2.0, "house")
        self.assertAlmostEqual(score["structural_plus_incumbency"]["brier"], (structural_p - 1) ** 2, places=7)
        self.assertAlmostEqual(score["structural_plus_generic_ballot"]["brier"], (prior_p - 1) ** 2, places=7)
        self.assertLess(score["brier_delta_generic_minus_structural"], 0)
        self.assertLess(score["brier_delta_full_minus_prior"], 0)

    def test_structural_decomposition_excludes_non_two_party_contests(self):
        preds = [
            {
                "race_code": "A",
                "race_type": "house",
                "dem_candidate": "Dem Candidate",
                "rep_candidate": "Rep Candidate",
                "prior_margin": 0.0,
                "dem_probability": 0.5,
                "poll_count": 0,
            },
            {
                "race_code": "B",
                "race_type": "house",
                "dem_candidate": "(No Democrat)",
                "rep_candidate": "Rep Candidate",
                "prior_margin": -20.0,
                "dem_probability": 0.001,
                "poll_count": 0,
            },
        ]
        score = m.structural_decomposition(preds, {"A": 1, "B": 0}, 0.0)
        self.assertEqual(score["n"], 1)

    def test_structural_competitive_filter_is_fixed_20_80(self):
        preds = [
            {
                "race_code": "A",
                "race_type": "house",
                "dem_candidate": "D A",
                "rep_candidate": "R A",
                "prior_margin": 0.0,
                "dem_probability": 0.6,
                "poll_count": 1,
            },
            {
                "race_code": "B",
                "race_type": "house",
                "dem_candidate": "D B",
                "rep_candidate": "R B",
                "prior_margin": 20.0,
                "dem_probability": 0.9,
                "poll_count": 1,
            },
        ]
        score = m.structural_decomposition(
            preds, {"A": 1, "B": 1}, 0.0, structural_competitive_only=True
        )
        self.assertEqual(score["n"], 1)
        self.assertEqual(score["sample"], "structural_20_80")

    def test_structural_confident_miss_is_exposed_not_removed(self):
        preds = [{
            "race_code": "A",
            "race_type": "house",
            "dem_candidate": "D A",
            "rep_candidate": "R A",
            "prior_margin": -10.0,
            "dem_probability": 0.3,
            "poll_count": 1,
        }]
        score = m.structural_decomposition(preds, {"A": 1}, 0.0)
        self.assertEqual(len(score["confident_structural_misses"]), 1)
        self.assertEqual(score["confident_structural_misses"][0]["race_code"], "A")
        self.assertLess(score["confident_structural_misses"][0]["winner_probability_structural"], 0.2)

    def test_paired_component_test_detects_improvement(self):
        preds = [
            {"race_code": "A", "race_type": "house", "prior_margin": 0.0, "dem_probability": 0.8, "poll_count": 2},
            {"race_code": "B", "race_type": "house", "prior_margin": 0.0, "dem_probability": 0.2, "poll_count": 1},
        ]
        score = m.paired_summary(preds, {"A": 1, "B": 0})
        self.assertEqual(score["state"], "scored")
        self.assertEqual(score["n"], 2)
        self.assertLess(score["brier_delta_with_polls_minus_prior"], 0)
        self.assertLess(score["log_loss_delta_with_polls_minus_prior"], 0)
        self.assertEqual(score["moved_toward_eventual_winner"], 2)

    def test_paired_component_test_detects_degradation(self):
        preds = [
            {"race_code": "A", "race_type": "house", "prior_margin": 4.0, "dem_probability": 0.2, "poll_count": 2},
        ]
        score = m.paired_summary(preds, {"A": 1})
        self.assertGreater(score["brier_delta_with_polls_minus_prior"], 0)
        self.assertEqual(score["moved_away_from_eventual_winner"], 1)

    def test_prior_competitive_filter_is_fixed_20_80(self):
        preds = [
            {"race_code": "A", "race_type": "house", "prior_margin": 0.0, "dem_probability": 0.6, "poll_count": 1},
            {"race_code": "B", "race_type": "house", "prior_margin": 20.0, "dem_probability": 0.9, "poll_count": 1},
        ]
        score = m.paired_summary(preds, {"A": 1, "B": 1}, prior_competitive_only=True)
        self.assertEqual(score["n"], 1)

    def test_transition_partition_preserves_later_denominator(self):
        previous = {
            "A": {"dem_probability": .4, "poll_count": 0},
            "B": {"dem_probability": .7, "poll_count": 1},
            "C": {"dem_probability": .2, "poll_count": 0},
        }
        current = {
            "A": {"dem_probability": .6, "poll_count": 1},
            "B": {"dem_probability": .6, "poll_count": 2},
            "C": {"dem_probability": .25, "poll_count": 0},
        }
        part = m.transition_partition(previous, current, {"A": 1, "B": 0, "C": 0})
        self.assertEqual(part["later_polled"]["n"] + part["later_unpolled"]["n"], 3)
        self.assertEqual(part["newly_polled"]["n"], 1)

    def test_roster_transition_is_labelled_not_removed(self):
        previous = {
            "A": {"race_type": "house", "dem_candidate": "D", "rep_candidate": None, "dem_probability": .999},
            "B": {"race_type": "house", "dem_candidate": "D2", "rep_candidate": "R2", "dem_probability": .55},
        }
        current = {
            "A": {"race_type": "house", "dem_candidate": "D", "rep_candidate": "R", "dem_probability": .001},
            "B": {"race_type": "house", "dem_candidate": "D2", "rep_candidate": "R2", "dem_probability": .50},
        }
        result = m.roster_transitions(previous, current, {"A": 0, "B": 1})
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["large_movement_count"], 1)
        self.assertEqual(result["changes"][0]["race_code"], "A")
        self.assertEqual(result["changes"][0]["dem_probability_before"], .999)
        self.assertEqual(result["changes"][0]["dem_probability_after"], .001)


if __name__ == "__main__":
    unittest.main()
