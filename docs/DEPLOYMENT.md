# Deployment

MIDTERM SIGNALS is deployed as a static Cloudflare Pages project.

- Repository: `MusicOfScience/midterm-signals`
- Production branch: `main`
- Output directory: `public`
- Cloudflare build command: none
- Canonical URL: https://midterm-signals.pages.dev

The GitHub `forecast.yml` workflow refreshes public data twice daily and on relevant pushes to `main`. It builds the model, validates numerical output, runs unit/static checks, generates immutable history and deep routes, and commits only after those gates pass.

Cloudflare therefore receives a checked, self-contained static bundle. A failed upstream refresh leaves the last healthy deployment intact.
