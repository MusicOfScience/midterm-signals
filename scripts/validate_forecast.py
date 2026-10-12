#!/usr/bin/env python3
"""Fail-closed numerical validation for MIDTERM SIGNALS v0.2 output."""
from __future__ import annotations
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P = ROOT / 'public' / 'data' / 'forecast.json'

def assert_prob(x, label):
    if not isinstance(x, (int, float)) or not math.isfinite(x) or not (0 <= x <= 1):
        raise AssertionError(f'{label}: invalid probability {x!r}')

def main():
    data = json.loads(P.read_text())
    assert data['schema_version'] == '0.2.0'
    assert data['production_forecast'] == 'published'
    assert data['election_date'] == '2026-11-03'
    races = data['races']
    house = [r for r in races if r['race_type'] == 'house']
    senate = [r for r in races if r['race_type'] == 'senate']
    assert len(house) == 435, len(house)
    assert len({r['race_code'] for r in house}) == 435
    assert len(senate) >= 33, len(senate)
    assert len({r['race_code'] for r in senate}) == len(senate)
    for r in races:
        assert_prob(r['dem_probability'], r['race_code'])
        m = r['forecast_margin_d_minus_r']
        assert isinstance(m, (int, float)) and math.isfinite(m)
    for chamber in ('house', 'senate'):
        s = data['summary'][chamber]
        assert_prob(s['dem_control_probability'], f'{chamber} D control')
        assert_prob(s['rep_control_probability'], f'{chamber} R control')
        assert abs(s['dem_control_probability'] + s['rep_control_probability'] - 1) < 1e-6
        assert s['dem_seats_80_interval'][0] <= s['expected_dem_seats'] <= s['dem_seats_80_interval'][1]
        assert s['simulations'] >= 10_000
    assert data['summary']['house']['control_threshold_dem'] == 218
    assert data['summary']['senate']['control_threshold_dem'] == 51
    assert data['national_environment']['polls_in_35_day_window'] > 0
    assert data['provenance']['upstream_commit']
    assert data['provenance']['input_sha256']
    print(f"Forecast valid: 435 House, {len(senate)} Senate, {data['summary']['house']['simulations']:,} simulations")

if __name__ == '__main__':
    main()
