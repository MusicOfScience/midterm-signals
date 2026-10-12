# Cloudflare Pages deployment

## Git integration

Create a Cloudflare Pages project connected to `MusicOfScience/midterm-signals`.

- Production branch: `main`
- Framework preset: None
- Build command: leave blank
- Build output directory: `public`
- Root directory: repository root

No secrets are required for the current static publication.

## Wrangler deployment

After Cloudflare authentication:

```bash
npx wrangler pages deploy public --project-name midterm-signals
```

`wrangler.toml` declares the Pages output directory.

## Verification

After every production deployment:

1. request the production URL;
2. verify a 2xx response;
3. confirm the overview renders;
4. open `data/status.json`;
5. confirm the publication gate shown in the UI agrees with the machine-readable status;
6. inspect the browser console for runtime errors.
