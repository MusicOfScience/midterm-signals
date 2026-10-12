# Architecture

MIDTERM SIGNALS is a static publication backed by a deterministic, source-controlled forecasting pipeline.

```text
public observations
      |
      v
data/raw/YYYY-MM-DD/  <---- immutable dated snapshot
      |
      +---- data/reference/ historical calibration
      |
      v
scripts/build_forecast.py
      |
      +---- model specification + deterministic seed
      |
      v
public/data/forecast.json
public/data/status.json
public/data/history/YYYY-MM-DD.json
      |
      v
public/index.html + app.js + styles.css
      |
      v
Cloudflare Pages
```

Raw observations are dated and preserve nulls. `build_forecast.py` is the only numerical transformation in v0.1 and has no network access. Derived output carries model metadata, input hashes and limitations. The browser reads precomputed JSON and fails closed if it cannot load it. Published forecast runs are archived rather than overwritten.

The House is a hybrid national seat-vote/current-map model. The Senate is race-based, polling-plus-rating, with correlated errors. Joint chamber control is simulated with a shared national shock. Qualitative intelligence, LLM judgement and presidential approval do not alter v0.1 probabilities.
