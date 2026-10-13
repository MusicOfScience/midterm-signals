#!/usr/bin/env python3
from pathlib import Path
_parts = sorted((Path(__file__).with_name('build_forecast_parts')).glob('*.pyfrag'), key=lambda p: int(p.stem))
_source = ''.join(p.read_text() for p in _parts)
exec(compile(_source, __file__, 'exec'), globals(), globals())
