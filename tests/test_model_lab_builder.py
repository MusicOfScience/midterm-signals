import importlib.util
import inspect
from datetime import date
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / "scripts" / "build_model_lab.py"
spec = importlib.util.spec_from_file_location("build_model_lab", P)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ModelLabBuilderTests(unittest.TestCase):
    def test_scoreability_gate_cannot_accept_results(self):
        params = inspect.signature(m.fixed_sample_scoreability).parameters
        self.assertEqual(list(params), ["races", "election"])
        self.assertNotIn("results", params)
        self.assertNotIn("outcomes", params)

    def test_unstable_major_party_presence_is_excluded_from_fixed_sample(self):
        rows = []
        for day, rep in [("2018-08-01", ""), ("2018-11-02", "Republican")]:
            rows.append({
                "race_code": "XX-01",
                "known_date": day,
                "dem_name": "Democrat",
                "rep_name": rep,
            })
        gate = m.fixed_sample_scoreability(rows, date(2018, 11, 6))
        self.assertEqual(gate["state"], "frozen_pre_outcome")
        self.assertFalse(gate["uses_outcomes"])
        self.assertEqual(gate["admitted_races"], 0)
        self.assertEqual(gate["excluded_races"], 1)
        self.assertEqual(gate["exclusions"][0]["reason"], m.PRESENCE_EXCLUSION)

    def test_stable_presence_allows_candidate_identity_change(self):
        rows = [
            {"race_code": "XX-01", "known_date": "2018-08-01", "dem_name": "Dem A", "rep_name": "Rep"},
            {"race_code": "XX-01", "known_date": "2018-10-01", "dem_name": "Dem B", "rep_name": "Rep"},
        ]
        gate = m.fixed_sample_scoreability(rows, date(2018, 11, 6))
        self.assertEqual(gate["admitted_race_codes"], ["XX-01"])
        self.assertEqual(gate["excluded_races"], 0)

    def test_official_admitted_samples_and_partitions(self):
        payload = m.build()
        self.assertEqual(payload["summary"]["state"], "scored")
        cycles = {c["cycle"]: c for c in payload["cycles"]}
        expected = {2018: 468, 2022: 416}
        for year, n in expected.items():
            cycle = cycles[year]
            self.assertEqual(cycle["scoreability"]["admitted_races"], n)
            self.assertTrue(cycle["scoreability"]["uses_outcomes"] is False)
            for cp in cycle["checkpoints"]:
                self.assertEqual(cp["score"]["state"], "scored")
                self.assertEqual(cp["score"]["n"], n)
                self.assertEqual(sum(b["count"] for b in cp["score"]["calibration"]), n)
                self.assertEqual(
                    cp["score"]["polling"]["polled"]["n"] + cp["score"]["polling"]["unpolled"]["n"],
                    n,
                )
                chamber_n = sum(v["n"] for v in cp["score"]["chambers"].values() if v["state"] == "scored")
                self.assertEqual(chamber_n, n)
            self.assertEqual(cycle["movement"]["common_race_count"], n)

        exclusions_2018 = {row["race_code"]: row["reason"] for row in cycles[2018]["scoreability"]["exclusions"]}
        self.assertEqual(exclusions_2018, {
            "LA-06": m.PRESENCE_EXCLUSION,
            "OR-03": m.PRESENCE_EXCLUSION,
        })
        self.assertEqual(cycles[2022]["scoreability"]["excluded_races"], 0)
        self.assertEqual(cycles[2022]["chamber_scope"]["senate"]["state"], "unavailable")


if __name__ == "__main__":
    unittest.main()
