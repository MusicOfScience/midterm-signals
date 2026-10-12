# Deployment

MIDTERM SIGNALS is a static Cloudflare Pages site.

- Repository: `MusicOfScience/midterm-signals`
- Branch: `main`
- Output directory: `public`
- Build command: none
- Canonical Pages URL: https://midterm-signals.pages.dev

The numerical model is built before deployment. Cloudflare receives a complete static publication bundle without Python/model dependencies. GitHub Actions rebuilds the model from checked-in inputs, validates it and fails if committed derived artifacts differ from a deterministic rebuild.

Manual fallback: `npx wrangler pages deploy public --project-name midterm-signals`. Authentication belongs in secret storage, never the repository.
