import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "scripts" / "model_lab_diagnostics.py"
spec = importlib.util.spec_from_file_location("model_lab_diagnostics", P)
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)


class ModelLabDiagnosticsTests(unittest.TestCase):
    def test_diagnostic_contract_is_fixed(self):
        self.assertEqual(d.DAYS, (60, 30, 14, 7, 1))
        self.assertEqual(d.BANDS, (
            ("45-55", .45, .55), ("40-60", .40, .60),
            ("30-70", .30, .70), ("20-80", .20, .80),
        ))
        self.assertEqual(d.MOVE, .10)
        self.assertEqual(d.CONF, .80)

    def test_calibration_bins_preserve_counts_and_residuals(self):
        probs = [.05, .15, .51, .55, .94]
        outcomes = [0, 0, 1, 0, 1]
        bins = d.bins(probs, outcomes)
        self.assertEqual(sum(b["count"] for b in bins), len(probs))
        for b in bins:
            self.assertAlmostEqual(b["calibration_residual"], round(b["observed_rate"] - b["mean_probability"], 6), places=6)

    def test_competitive_safe_complement_preserves_denominator(self):
        probs = [.10, .25, .35, .46, .52, .65, .75, .90]
        predictions = [{"race_code": str(i), "dem_probability": p, "rep_probability": 1-p, "race_type": "house", "poll_count": 0} for i, p in enumerate(probs)]
        results = {str(i): int(p >= .5) for i, p in enumerate(probs)}
        base = d.metrics(predictions, results)
        cp = {"state":"scored", "predictions":predictions, "score":{"state":"scored", "n":len(predictions), "brier":base["brier"], "log_loss":base["log_loss"]}}
        d.enrich_score(cp, results)
        rows = {r["band"]: r for r in cp["score"]["competitive_bands"]}
        self.assertEqual(rows["45-55"]["n"], 2)
        self.assertEqual(rows["20-80"]["n"] + rows["safe-outside-20-80"]["n"], len(predictions))

    def test_polling_and_chamber_partitions_preserve_denominator(self):
        predictions = [
            {"race_code":"H1","dem_probability":.6,"rep_probability":.4,"race_type":"house","poll_count":2},
            {"race_code":"H2","dem_probability":.4,"rep_probability":.6,"race_type":"house","poll_count":0},
            {"race_code":"S1","dem_probability":.55,"rep_probability":.45,"race_type":"senate","poll_count":1},
        ]
        results = {"H1":1,"H2":0,"S1":0}
        base = d.metrics(predictions, results)
        cp = {"state":"scored", "predictions":predictions, "score":{"state":"scored", "n":3, "brier":base["brier"], "log_loss":base["log_loss"]}}
        d.enrich_score(cp, results)
        polling = cp["score"]["polling"]
        chambers = cp["score"]["chambers"]
        self.assertEqual(polling["polled"]["n"] + polling["unpolled"]["n"], 3)
        self.assertEqual(chambers["house"]["n"] + chambers["senate"]["n"], 3)

    def test_committed_admitted_cycles_pass_all_invariants(self):
        payload = json.loads((ROOT / "public" / "data" / "model-lab.json").read_text())
        self.assertEqual(payload["schema_version"], "1.1.0")
        self.assertEqual(payload["model_contract"]["state"], "verified")
        cycles = {int(c["cycle"]): c for c in payload["cycles"]}
        self.assertEqual(set(cycles), {2018, 2022})
        expected = {2018: 470, 2022: 416}
        for year, n in expected.items():
            cycle = cycles[year]
            self.assertEqual(cycle["state"], "scored")
            self.assertEqual([cp["days_to_election"] for cp in cycle["checkpoints"]], list(d.DAYS))
            for cp in cycle["checkpoints"]:
                score = cp["score"]
                self.assertEqual(score["state"], "scored")
                self.assertEqual(score["n"], n)
                self.assertEqual(len(cp["predictions"]), n)
                self.assertEqual(sum(b["count"] for b in score["calibration"]), n)
                self.assertEqual(score["polling"]["polled"]["n"] + score["polling"]["unpolled"]["n"], n)
                self.assertEqual(sum(v["n"] for v in score["chambers"].values() if v["state"] == "scored"), n)
                wide = next(b for b in score["competitive_bands"] if b["band"] == "20-80")
                safe = next(b for b in score["competitive_bands"] if b["band"] == "safe-outside-20-80")
                self.assertEqual(wide["n"] + safe["n"], n)
            self.assertEqual(cycle["movement"]["common_race_count"], n)
            for transition in cycle["movement"]["transitions"]:
                groups = transition["polling_status_movement"]
                self.assertEqual(sum(g["n"] for g in groups.values()), n)
        self.assertEqual(cycles[2022]["chamber_scope"]["senate"]["state"], "unavailable")
        self.assertEqual(cycles[2022]["chamber_scope"]["senate"]["race_counts_by_checkpoint"], [0,0,0,0,0])
        self.assertEqual(cycles[2018]["chamber_scope"]["senate"]["state"], "scored")


if __name__ == "__main__":
    unittest.main()
