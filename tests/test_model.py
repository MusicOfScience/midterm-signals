import importlib.util
from pathlib import Path
import unittest

P=Path(__file__).resolve().parents[1]/'scripts/build_forecast.py'
spec=importlib.util.spec_from_file_location('build_forecast',P)
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

class ModelTests(unittest.TestCase):
    def test_rating(self):
        self.assertEqual(m.rating(.5),'Toss-up')
        self.assertEqual(m.rating(.8),'Likely D')
        self.assertEqual(m.rating(.1),'Safe R')
    def test_relative_lean(self):
        row={'margin_2016':'2.09','margin_2020':'4.46','margin_2024':'-1.47'}
        self.assertAlmostEqual(m.relative_lean(row),0,places=6)
    def test_summary_intervals(self):
        out=m.summarize_counts([217,218,219,220]*25,435,218,220)
        self.assertAlmostEqual(out['dem_control_probability'],.75)
        self.assertEqual(sum(x['probability'] for x in out['distribution']),1)
        self.assertEqual(out['control_threshold_dem'],218)
    def test_candidate_match(self):
        self.assertTrue(m.candidate_match('Jane Smith','Jane Smith'))
        self.assertFalse(m.candidate_match('Jane Smith','John Doe'))

if __name__=='__main__': unittest.main()
