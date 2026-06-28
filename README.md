# ResumeRadar — Frontend Redesign

A production-grade React + Tailwind + Framer Motion frontend for the existing
Flask resume analyzer backend. **Zero backend code was touched** — every
endpoint, request payload, and response shape in `app.py` is used exactly as
it already exists.

## What this is, file-by-file

You asked for `index.html` / `style.css` / `script.js` + React components.
Because React, Tailwind, and Framer Motion all require a build step, those
three map onto a real project like this:

| You asked for | What it became here | Why |
|---|---|---|
| `index.html` | `index.html` (Vite entry) | Same role — loads fonts, mounts the app |
| `style.css` | `src/index.css` | Tailwind directives + design tokens + the scan-line motif CSS |
| `script.js` | `src/api/client.js` + `src/main.jsx` | All Axios/API logic lives in one file, exactly like the old `script.js` did |
| React components | `src/components/**`, `src/pages/**` | ~25 focused component files, see structure below |

There is no plain "index.html with inline script" anymore — running this
requires Node (Vite dev server / build), the same as any React+Tailwind app.

## Project structure

```
src/
├── api/client.js              # every backend call lives here — start here
│                               #   to confirm nothing about the API changed
├── context/AuthContext.jsx     # session state (login/signup/logout/me)
├── components/
│   ├── layout/                 # Navbar, Footer
│   ├── landing/                # Hero, HowItWorks, BenefitsGrid, CTASection
│   ├── auth/                   # AuthModal (login + signup)
│   ├── dashboard/               # Upload, scanning loader, score ring,
│   │                            # heatmap, result/suggestion cards, history
│   └── ui/                      # Alert, AnimatedNumber
├── pages/Landing.jsx, Dashboard.jsx
├── utils/                       # score-color logic, file validation
└── App.jsx / main.jsx
```

## Setup

```bash
npm install
cp .env.example .env     # optional — defaults to your existing Render URL
npm run dev              # http://localhost:3000
```

```bash
npm run build             # outputs static files to dist/
npm run preview           # sanity-check the production build locally
```

## The one thing you may need to touch — and it's not code

Your backend's CORS allow-list (`ALLOWED_ORIGINS` env var on Render) is what
decides which frontend origins are allowed to send the session cookie. **This
is an environment variable, not a Python code change**, so it doesn't violate
"don't modify backend logic":

- Local dev: Vite is configured to run on **port 3000**, matching the
  backend's existing default (`http://localhost:3000`), so local dev works
  with no changes at all.
- Production: once you deploy this frontend (Vercel, Netlify, etc.), add its
  URL to `ALLOWED_ORIGINS` in your Render dashboard, e.g.
  `ALLOWED_ORIGINS=https://your-frontend.vercel.app`.

## One labeling note (no data or logic changed)

`Resume.to_dict()` returns a field called `detected_experience` whose value
is actually `detected_soft_skills` from `analyze_resume()` — the backend
saves soft-skills data under that key. I left this completely untouched, but
in the UI I labeled the corresponding card "Strengths detected" rather than
"Experience," since that's an accurate description of what's actually in
that field. Purely a frontend label — the JSON key and its contents are
exactly what your backend already sends.

## Design direction

Light, instrument-panel aesthetic (white/near-white canvas, signal-blue
accent, mono numerals for scores) built around one recurring idea: a scan
line sweeping over a document, echoed in the hero, the upload loader, and
implied by the heatmap grid — visualizing "this is what the ATS sees" rather
than a generic purple-gradient SaaS template.
