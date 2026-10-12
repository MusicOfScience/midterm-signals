# Model v0.2

MIDTERM SIGNALS v0.2 is a transparent House/Senate baseline intended to make every numerical transformation inspectable.

## National environment

Generic-ballot polls ending in the most recent 35 days are averaged with exponential recency decay (11-day half-life), pollster-quality weighting and square-root sample-size weighting. Polls carrying a partisan sponsor flag are downweighted. Missing polls are never imputed.

## Race prior

For each 2026 House district or Senate state, presidential D-R margins are converted into *relative* partisan lean by subtracting the national D-R result in that year. The race prior uses 5% of 2016, 20% of 2020 and 75% of 2024 relative lean, then adds the current generic-ballot environment and a modest incumbency term.

## Race polling

Nominee-matched polls ending within 55 days are aggregated with similar recency/quality/sample weighting. Their influence rises sub-linearly with poll count and is capped, so a small number of polls cannot erase the structural prior.

## Probability and chamber simulation

Race margins are mapped to Democratic win probability with a normal-error model. House and Senate chamber control are estimated with 30,000 deterministic Monte Carlo draws. Each draw contains both a common national shock and race-specific error so uncertainty can move many races together.

House control requires 218 seats. Democratic Senate control is defined as 51 caucus seats because the vice president is Republican; a 50-50 Senate therefore remains Republican-controlled for organizational/tie-breaking purposes.

## Hard boundary

News text, endorsements, strategist commentary and LLM judgement are not numerical model inputs. A future feature may be admitted only through a documented, testable model-version change.
