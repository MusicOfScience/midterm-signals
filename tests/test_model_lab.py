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
        self.assertEqual(state["contract_fingerprint_sha256"], m.contract_fingerprint())

    def test_diagnostic_thresholds_are_fixed(self):
        self.assertEqual(m.CHECKPOINT_DAYS, (60, 30, 14, 7, 1))
        self.assertEqual(m.COMPETITIVE_BANDS, (
            ("45-55", 0.45, 0.55),
            ("40-60", 0.40, 0.60),
            ("30-70", 0.30, 0.70),
            ("20-80", 0.20, 0.80),
        ))
        self.assertEqual(m.MOVEMENT_THRESHOLD, 0.10)
        self.assertEqual(m.CONFIDENT_MISS_THRESHOLD, 0.80)

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

    def test_calibration_bins_preserve_counts_and_residuals(self):
        p = [0.05, 0.15, 0.51, 0.55, 0.94]
        y = [0, 0, 1, 0, 1]
        bins = m.calibration_bins(p, y)
        self.assertEqual(sum(b["count"] for b in bins), len(p))
        for b in bins:
            self.assertAlmostEqual(
                b["calibration_residual"],
                round(b["observed_rate"] - b["mean_probability"], 6),
                places=6,
            )

    def test_competitive_and_safe_partition_invariant(self):
        probs = [0.10, 0.25, 0.35, 0.46, 0.52, 0.65, 0.75, 0.90]
        preds = [
            {"race_code": str(i), "dem_probability": p, "rep_probability": 1-p, "race_type": "house", "poll_count": 0}
            for i, p in enumerate(probs)
        ]
        results = {str(i): int(p >= 0.5) for i, p in enumerate(probs)}
        bands = {row["band"]: row for row in m.competitive_diagnostics(preds, results)}
        self.assertEqual(bands["45-55"]["n"], 2)
        self.assertEqual(bands["40-60"]["n"], 2)
        self.assertEqual(bands["30-70"]["n"], 4)
        self.assertEqual(bands["20-80"]["n"], 6)
        self.assertEqual(bands["20-80"]["n"] + bands["safe-outside-20-80"]["n"], len(preds))

    def test_poll_and_chamber_partitions_preserve_denominators(self):
        preds = [
            {"race_code": "H1", "dem_probability": .6, "rep_probability": .4, "race_type": "house", "poll_count": 2},
            {"race_code": "H2", "dem_probability": .4, "rep_probability": .6, "race_type": "house", "poll_count": 0},
            {"race_code": "S1", "dem_probability": .55, "rep_probability": .45, "race_type": "senate", "poll_count": 1},
        ]
        results = {"H1": 1, "H2": 0, "S1": 0}
        score = m.score_checkpoint(preds, results)
        self.assertEqual(score["polling"]["polled"]["n"] + score["polling"]["unpolled"]["n"], score["n"])
        self.assertEqual(score["chambers"]["house"]["n"] + score["chambers"]["senate"]["n"], score["n"])

    def test_movement_uses_frozen_predictions_then_results(self):
        checkpoints = []
        for day, pa, pb in [(60,.4,.7),(30,.5,.65),(14,.6,.6),(7,.65,.55),(1,.75,.45)]:
            checkpoints.append({
                "state": "scored",
                "days_to_election": day,
                "predictions": [
                    {"race_code":"A","dem_probability":pa,"rep_probability":1-pa,"race_type":"house","poll_count":1},
                    {"race_code":"B","dem_probability":pb,"rep_probability":1-pb,"race_type":"house","poll_count":0},
                ],
            })
        movement = m.movement_diagnostics(checkpoints, {"A": 1, "B": 0})
        self.assertEqual(movement["common_race_count"], 2)
        self.assertTrue(movement["strongest_toward_eventual_winner"][0]["strong_toward_winner"])

    def test_replay_probability_does_not_accept_results(self):
        self.assertNotIn("results", m.race_probability.__code__.co_varnames[:m.race_probability.__code__.co_argcount])

    def test_admitted_cycle_denominators_and_partitions(self):
        payload = m.build()
        self.assertEqual(payload["summary"]["state"], "scored")
        cycles = {c["cycle"]: c for c in payload["cycles"]}
        expected = {2018: 470, 2022: 416}
        for year, n in expected.items():
            cycle = cycles[year]
            self.assertEqual([cp["days_to_election"] for cp in cycle["checkpoints"]], list(m.CHECKPOINT_DAYS))
            for cp in cycle["checkpoints"]:
                self.assertEqual(cp["score"]["state"], "scored")
                self.assertEqual(cp["score"]["n"], n)
                self.assertEqual(sum(b["count"] for b in cp["score"]["calibration"]), n)
                self.assertEqual(cp["score"]["polling"]["polled"]["n"] + cp["score"]["polling"]["unpolled"]["n"], n)
                chamber_n = sum(v["n"] for v in cp["score"]["chambers"].values() if v["state"] == "scored")
                self.assertEqual(chamber_n, n)
            self.assertEqual(cycle["movement"]["common_race_count"], n)
        self.assertEqual(cycles[2022]["chamber_scope"]["senate"]["state"], "unavailable")
        self.assertGreater(min(cycles[2018]["chamber_scope"]["senate"]["race_counts_by_checkpoint"]), 0)


if __name__ == "__main__":
    unittest.main()
