# Landing page (`site/`)

Public marketing page for Legal Document Chat. **Static** (HTML/CSS/JS, no build step). This
is the *public* page — distinct from the air-gapped app — so it uses web fonts (Google
Fonts) and links out to Ollama + the GitHub Releases download. The app itself stays
loopback-only with self-hosted assets.

## Preview locally
```bash
cd ~/projects/legal-doc-intelligence/site
python3 -m http.server 4173
# open http://127.0.0.1:4173
```

## Hosting (wired, deploy later — D-58 v1)
- **GitHub Pages:** either set Pages → Source → `main` / `/site`, or run the manual workflow
  `.github/workflows/deploy-site.yml` (Actions → "Deploy landing page" → Run workflow). The
  workflow is `workflow_dispatch`-only so it never deploys on push.
- **GitHub Releases:** the "Download for macOS" CTA points at
  `https://github.com/janderswag/legal-document-chat/releases` — update the owner/repo slug,
  then attach the launcher build to a Release.

## Top follow-up
Replace the framed demo placeholder (`#demo-placeholder` in `index.html`) with a real screen
capture (GIF/MP4) of an answer + its verified citation opening the source at the cited page.
