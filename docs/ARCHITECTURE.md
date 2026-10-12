# Architecture

MIDTERM SIGNALS is deliberately layered so that presentation cannot silently mutate the analytical record.

## Publication layers

1. **Raw observations** — source-native material and immutable retrieval snapshots.
2. **Processed observations** — normalized polling, race, fundamentals and metadata tables.
3. **Polling aggregation** — poll estimates with uncertainty, kept distinct from forecast outputs.
4. **Election forecast** — probabilistic House/Senate simulations produced only from documented numerical inputs.
5. **Third-party forecasts** — ratings and probabilities from external forecasters, stored as observations rather than blended invisibly into the model.
6. **Qualitative intelligence** — campaign/news information, explicitly non-numerical unless a documented model feature is later approved.
7. **Scenarios** — counterfactual runs separated from the baseline forecast.
8. **Results** — actual election outcomes, never back-written into pre-election snapshots.

## Safety boundary

The current public site is a projection layer. It presents the state of the publication gate and does not claim live probabilities while required inputs and validation are incomplete.

Future pipeline work should preserve immutable historical snapshots, deterministic build artefacts where possible, input hashes, model version identifiers and a run manifest for each production forecast.
