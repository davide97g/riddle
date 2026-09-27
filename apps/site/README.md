# apps/site

The landing page, [get-riddle.davideghiotto.it](https://get-riddle.davideghiotto.it).
Static HTML, CSS and one script, no build step, served by nginx.

Every line of handwriting on it is the diary's own: `tools/make_strokes.py`
lays the replies out with the code the loop uses to answer on the tablet
(`riddle.tools.handwriting.ink`) and writes the pen paths to
`assets/strokes.json`, which the page draws stroke by stroke. The questions
are in a Hershey script, a different hand, because they stand for yours. The
wordmark is `apps/web/src/lib/wordmark.ts`.

```bash
.venv/bin/python apps/site/tools/make_strokes.py   # after changing a line, a font or the hand
python3 -m http.server -d apps/site 8811           # look at it
```

The screenshots in `assets/img` are the iPhone app against a scratch server
with invented entries (a separate `RIDDLE_VAR`, never the real diary). The
icon renders are `ictool` exports of `apps/apple/Riddle/AppIcon.icon`.

## Deploying

A Dokploy compose app on the homelab, built from this repository
(`apps/site/compose.yml`, branch `main`), published on the box's Cloudflare
tunnel: `get-riddle.davideghiotto.it` -> `http://localhost:80`, where Traefik
routes it by host. Dokploy's auto-deploy is off, as for everything on that
box; a release is one `compose.deploy` call. The runbook for all of that is
the homelab repository's `docs/porting-to-homelab.md`.

The Download for Mac buttons point at the latest GitHub release's
`Riddle-<version>.dmg`, built by `apps/apple/package.sh`. A new version means
a new release and the file name in `index.html`.
