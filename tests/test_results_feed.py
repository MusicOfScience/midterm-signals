import json
import tempfile
import unittest
from pathlib import Path
from scripts.refresh_results import model_code, normalize, publish


def sample(votes=100, called=False):
    return {"generated_at": "2026-11-04T01:00:00Z", "races": {
        "H-PA-07": {"cands": [
            {"name": "A", "party": "D", "votes": votes, "winner": called},
            {"name": "B", "party": "R", "votes": 80, "winner": False},
        ], "called_by": "AP" if called else "", "url": "https://example.org/pennsylvania"},
        "S-OH-sp": {"cands": [{"name": "C", "party": "D", "votes": 0}, {"name": "D", "party": "R", "votes": 0}]},
    }}


class ResultsFeedTests(unittest.TestCase):
    def test_model_keys_and_congressional_units(self):
        self.assertEqual(model_code("H-AK-00"), ("AK-01", "house", "AK"))
        self.assertIsNone(model_code("H-CA-00"))
        self.assertEqual(model_code("S-OH-sp"), ("OH-SEN", "senate", "OH"))
        self.assertIsNone(model_code("G-PA"))

    def test_empty_not_fabricated(self):
        data = normalize({"generated_at": None, "races": {}}, "now")
        self.assertEqual(data["state"], "awaiting_results")
        self.assertEqual(data["races"], [])

    def test_lead_not_call_and_zero_not_missing(self):
        data = normalize(sample(), "now")
        race = next(r for r in data["races"] if r["model_code"] == "PA-07")
        self.assertEqual(race["votes_total"], 180)
        self.assertEqual(race["leader"]["party"], "D")
        self.assertFalse(race["called"])
        self.assertEqual(race["source_name"], "The People's Tally")
        senate = next(r for r in data["races"] if r["model_code"] == "OH-SEN")
        self.assertEqual(senate["votes_total"], 0)

    def test_called_requires_named_source(self):
        self.assertTrue(next(r for r in normalize(sample(called=True), "now")["races"]
                             if r["model_code"] == "PA-07")["called"])
        x = sample(called=True)
        x["races"]["H-PA-07"]["called_by"] = ""
        self.assertFalse(next(r for r in normalize(x, "now")["races"]
                              if r["model_code"] == "PA-07")["called"])

    def test_never_overwrite_good_with_empty_or_malformed(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "observed.json"
            first = normalize(sample(), "first")
            self.assertEqual(publish(first, path), "updated")
            updated = normalize(sample(), "second")
            self.assertEqual(publish(updated, path), "unchanged")
            with self.assertRaises(ValueError):
                publish(normalize({"races": {}}, "third"), path)
            self.assertEqual(json.loads(path.read_text())["fetched_at"], "first")
            with self.assertRaises(ValueError):
                normalize({"races": []}, "bad")

    def test_invalid_vote_and_malformed_payload(self):
        x = sample(votes=-5)
        data = normalize(x, "now")
        race = next(r for r in data["races"] if r["model_code"] == "PA-07")
        self.assertEqual(race["votes_total"], 80)


if __name__ == "__main__":
    unittest.main()
