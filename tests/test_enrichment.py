import importlib.util
import pathlib
import unittest
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("enrich_outputs", ROOT / "scripts" / "enrich_outputs.py")
E = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(E)


class EnrichmentTests(unittest.TestCase):
    def test_inside_elections_house_mapping_preserves_production_code(self):
        races = [
            {"race_code": "IA-01", "race_type": "house", "state": "IA", "district": "01"},
            {"race_code": "IA-SEN", "race_type": "senate", "state": "IA", "district": "SEN"},
        ]
        self.assertEqual(
            E.normalise_rating_race({"state": "ia", "district": "1"}, "house", races),
            "IA-01",
        )
        self.assertEqual(
            E.normalise_rating_race({"state": "ia", "district": "IA"}, "senate", races),
            "IA-SEN",
        )

    def test_fec_candidate_matching_requires_surname_and_race_party(self):
        race = {"race_code": "IA-SEN", "race_type": "senate", "state": "IA", "district": "SEN"}
        rows = [
            {
                "CAND_ID": "S6IA00001",
                "CAND_NAME": "TUREK, JOSH",
                "CAND_PTY_AFFILIATION": "DEM",
                "CAND_OFFICE_ST": "IA",
                "CAND_OFFICE_DISTRICT": "00",
                "TTL_RECEIPTS": "1000000",
                "CVG_END_DT": "09/30/2026",
            },
            {
                "CAND_ID": "S6IA00002",
                "CAND_NAME": "HINSON, ASHLEY",
                "CAND_PTY_AFFILIATION": "REP",
                "CAND_OFFICE_ST": "IA",
                "CAND_OFFICE_DISTRICT": "00",
                "TTL_RECEIPTS": "2000000",
                "CVG_END_DT": "09/30/2026",
            },
        ]
        self.assertEqual(E.best_fec_match(rows, race, "D", "Josh Turek")["CAND_ID"], "S6IA00001")
        self.assertEqual(E.best_fec_match(rows, race, "R", "Ashley Hinson")["CAND_ID"], "S6IA00002")
        self.assertIsNone(E.best_fec_match(rows, race, "D", "Someone Else"))

    def test_signals_are_structured_and_external_context_has_no_model_effect(self):
        model = {
            "polls": [
                {"pollster": "Example", "end_date": "2026-10-10", "margin": 4.0, "source": "https://example.test/poll"}
            ],
            "races": [
                {
                    "race_code": "IA-SEN",
                    "race_type": "senate",
                    "dem_probability": 0.5,
                    "polls": [],
                    "dem_candidate": "Josh Turek",
                    "rep_candidate": "Ashley Hinson",
                }
            ],
            "provenance": {"upstream_input_mirror": "https://github.com/example/repo"},
        }
        inside = {
            "IA-SEN": {
                "rating": "Toss-up",
                "previous_rating": "Tilt Republican",
                "shift": "left",
                "updated_at": "2026-10-09",
                "source": "https://insideelections.com/ratings/senate/",
            }
        }
        signals = E.build_signals(model, inside, [], None, date(2026, 10, 13))
        self.assertGreaterEqual(len(signals), 2)
        poll = next(s for s in signals if s["category"] == "POLL")
        rating = next(s for s in signals if s["category"] == "RATING CHANGE")
        self.assertEqual(poll["model_effect"], "POLL INPUT")
        self.assertEqual(rating["model_effect"], "NONE")
        self.assertTrue(rating["source"].startswith("https://"))

    def test_numerical_fingerprint_ignores_contextual_enrichment(self):
        model = {
            "summary": {"house": {"dem_control_probability": 0.6}},
            "nowcast": {},
            "election_day_forecast": {},
            "tipping_point_house": [],
            "senate_battlegrounds": [],
            "national_environment": {"generic_ballot_d_minus_r": 4.2},
            "races": [{"race_code": "IA-SEN", "dem_probability": 0.5, "rep_probability": 0.5, "forecast_margin_d_minus_r": 0.0}],
        }
        before = E.numerical_fingerprint(model)
        model["external_forecasters"] = {"configured_count": 1}
        model["campaign_signals"] = [{"id": "x", "model_effect": "NONE"}]
        model["races"][0]["external_forecasters"] = {"Inside Elections": {"rating": "Toss-up"}}
        model["races"][0]["money"] = {"state": "current"}
        self.assertEqual(before, E.numerical_fingerprint(model))


if __name__ == "__main__":
    unittest.main()
