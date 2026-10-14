import importlib.util
import json
import pathlib
import unittest
from datetime import date
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("household_state", ROOT / "scripts" / "household_state.py")
H = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(H)


def obs(**kwargs):
    row = {
        "id": "x", "indicator": "X", "sensor": "x", "source": "Source", "source_id": "source",
        "source_type": "HIGH_QUALITY_PUBLIC_OPINION", "tier": 2, "data_reference_period": "2026-09",
        "fieldwork_start": None, "fieldwork_end": None, "publication_date": "2026-10-10",
        "retrieval_timestamp": "2026-10-15T00:00:00Z", "geographic_scope": "United States",
        "population_sample": "Adults", "methodology_notes": "Test", "freshness": "FRESH",
        "revision_status": "AS_PUBLISHED", "transformation_method": "NONE", "confidence": "HIGH",
        "forecast_effect": "NONE",
    }
    row.update(kwargs)
    return row


class HouseholdStateTests(unittest.TestCase):
    def test_freshness_boundaries(self):
        today = date(2026, 10, 15)
        self.assertEqual(H.freshness("2026-10-15", None, today), "FRESH")
        self.assertEqual(H.freshness("2026-09-14", None, today), "FRESH")
        self.assertEqual(H.freshness("2026-09-13", None, today), "RECENT")
        self.assertEqual(H.freshness("2026-04-18", None, today), "AGING")
        self.assertEqual(H.freshness("2026-04-17", None, today), "STALE")

    def test_affordability_single_energy_spike_does_not_force_acute(self):
        headline = obs(id="bls.cpi_all", sensor="affordability_pressure", yoy_pct_change=3.7, three_month_annualised_pct=None, change_since_january_2020_pct=25.0)
        gas = obs(id="bls.cpi_gasoline", sensor="affordability_pressure", yoy_pct_change=34.2)
        state = H.classify_affordability({"bls.cpi_all": headline, "bls.cpi_gasoline": gas})
        self.assertEqual(state["state"], "HIGH")
        self.assertEqual(state["forecast_effect"], "NONE")

    def test_real_income_loss_from_real_hourly_earnings(self):
        row = obs(id="bls.real_ahe_all_private", sensor="real_income_pressure", yoy_pct_change=-0.7)
        state = H.classify_real_income({"bls.real_ahe_all_private": row})
        self.assertEqual(state["state"], "MODEST REAL LOSS")

    def test_low_unemployment_alone_cannot_make_overall_labour_market_healthy(self):
        rate = obs(id="bls.unemployment_rate", sensor="labour_market_security", latest=4.2)
        labour, retention, mobility = H.classify_labour({"bls.unemployment_rate": rate}, {})
        self.assertEqual(labour["state"], "UNCERTAIN")
        self.assertEqual(retention["state"], "HEALTHY")
        self.assertEqual(mobility["state"], "UNCERTAIN")

    def test_jolts_levels_without_comparable_movement_do_not_make_mobility_healthy(self):
        rows = {
            "bls.unemployment_rate": obs(id="bls.unemployment_rate", sensor="labour_market_security", latest=4.2),
            "bls.job_openings": obs(id="bls.job_openings", sensor="labour_market_security", latest=7100, yoy_pct_change=None),
            "bls.hires": obs(id="bls.hires", sensor="labour_market_security", latest=5200, yoy_pct_change=None),
            "bls.quits": obs(id="bls.quits", sensor="labour_market_security", latest=3100, yoy_pct_change=None),
        }
        _, _, mobility = H.classify_labour(rows, {})
        self.assertEqual(mobility["state"], "UNCERTAIN")

    def test_partisan_breaking_requires_two_independent_high_quality_sources(self):
        baseline = {"states": {"partisan_deflection": "BREAKING"}}
        one = obs(id="pew.1", source="Pew", source_id="pew", sensor="partisan_deflection", state_contribution="BREAKING")
        state = H.survey_state_from_manual("partisan_deflection", [one], baseline, 2)
        self.assertEqual(state["state_status"], "PROVISIONAL_BASELINE_NOT_YET_TRIANGULATED")
        two = obs(id="gallup.1", source="Gallup", source_id="gallup", sensor="partisan_deflection", state_contribution="BREAKING")
        state = H.survey_state_from_manual("partisan_deflection", [one, two], baseline, 2)
        self.assertEqual(state["state"], "BREAKING")
        self.assertEqual(state["confidence"], "HIGH")
        self.assertTrue(state["triangulation_met"])

    def test_source_disagreement_is_preserved(self):
        baseline = {"states": {"economic_salience": "DOMINANT"}}
        a = obs(id="a", source_id="a", sensor="economic_salience", state_contribution="HIGH")
        b = obs(id="b", source_id="b", sensor="economic_salience", state_contribution="DOMINANT")
        state = H.survey_state_from_manual("economic_salience", [a, b], baseline, 2)
        self.assertEqual(state["state"], "UNCERTAIN")
        self.assertFalse(state["triangulation_met"])

    def test_k_shape_needs_two_domains(self):
        baseline = {"states": {"k_shaped_economy": "CLEARLY K-SHAPED"}}
        a = obs(id="a", source_id="jpm", sensor="k_shaped_economy", state_contribution="CLEARLY K-SHAPED", domain="spending")
        state = H.k_shaped_state_from_manual([a], baseline)
        self.assertEqual(state["state_status"], "PROVISIONAL_BASELINE_NOT_YET_TRIANGULATED")
        b = obs(id="b", source_id="nyfed", sensor="k_shaped_economy", state_contribution="CLEARLY K-SHAPED", domain="credit")
        state = H.k_shaped_state_from_manual([a, b], baseline)
        self.assertEqual(state["state"], "CLEARLY K-SHAPED")
        self.assertTrue(state["triangulation_met"])

    def test_composite_withholds_precision_when_evidence_coverage_is_low(self):
        states = {
            "affordability_pressure": H.state_record("affordability_pressure", "HIGH", "MODERATE", [], "test"),
            "real_income_pressure": H.state_record("real_income_pressure", "MODEST REAL LOSS", "MODERATE", [], "test"),
            "labour_market_security": H.provisional_sensor("labour_market_security", {"states": {"labour_market_security": "COOLING"}}),
            "household_cash_flow": H.provisional_sensor("household_cash_flow", {"states": {"household_cash_flow": "COMPRESSED"}}),
            "financial_buffer": H.provisional_sensor("financial_buffer", {"states": {"financial_buffer": "THIN"}}),
            "credit_stress": H.provisional_sensor("credit_stress", {"states": {"credit_stress": "CONCENTRATED STRESS"}}),
            "current_conditions": H.provisional_sensor("current_conditions", {"states": {"current_conditions": "VERY WEAK"}}),
        }
        result = H.stress_score(states)
        self.assertIsNone(result["score"])
        self.assertEqual(result["state"], "UNCERTAIN")
        self.assertIsNotNone(result["provisional_score"])

    def test_observation_validation_rejects_model_effect(self):
        bad = obs(forecast_effect="MANUAL ADJUSTMENT")
        with self.assertRaises(RuntimeError):
            H.validate_observations([bad])

    def test_source_health_marks_stale_observations_stale(self):
        registry = {"sources": [{"id": "x", "name": "X", "default_state": "MANUAL"}]}
        stale = obs(source_id="x", freshness="STALE")
        state = H.source_health(registry, [stale], {}, "2026-10-15T00:00:00Z")[0]
        self.assertEqual(state["state"], "STALE")

    def test_bls_fetch_chunks_series_requests(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self):
                return json.dumps({"status":"REQUEST_SUCCEEDED","message":[],"Results":{"series":[]}}).encode()
        with mock.patch.object(H.urllib.request, "urlopen", side_effect=[Response(), Response()]) as urlopen:
            result = H.fetch_bls(2025, 2026)
        self.assertEqual(result["status"], "REQUEST_SUCCEEDED")
        self.assertEqual(urlopen.call_count, 2)


if __name__ == "__main__":
    unittest.main()
