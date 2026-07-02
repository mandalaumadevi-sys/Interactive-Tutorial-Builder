# 🚀 Deploying Tuti — Frontend on Vercel, Backend on Render

This is a step-by-step, plain-English guide. Total time: ~30–40 minutes the first time.
Everything here uses **free tiers**.

Tuti has two parts that deploy separately:

| Part | What it is | Where it goes | Why |
|------|-----------|---------------|-----|
| **Frontend** | The React web UI | **Vercel** | Static site — fast, free, perfect for Vercel |
| **Backend** | FastAPI + LangGraph (the agents) | **Render** | Runs long builds + live updates — needs an always-on server, which Vercel can't do |

They talk to each other over the internet, so the last step is telling the frontend the backend's URL.

---

## Before you start — 3 accounts + 2 secrets

Create these (all free) and keep two values handy:

1. **GitHub** account — the code lives here; Render and Vercel deploy *from* it.
2. **OpenRouter** account → copy your **API key** (starts with `sk-or-...`). This pays for the LLM calls.
   → Keep this as **`OPENROUTER_API_KEY`**.
3. **Supabase** account → create a project → **Project Settings → Database → Connection string → URI**.
   → Keep this as **`SUPABASE_DB_URL`** (looks like `postgresql://postgres.<ref>:<password>@<host>:5432/postgres`).
   - ⚠️ If your password has special characters (`@ : / ?`), URL-encode them in the string.
   - Then open **Supabase → SQL Editor**, paste the contents of **`backend/supabase_schema.sql`**, and run it **once**. This creates the tables Tuti needs.

You'll paste those two secrets into Render's dashboard later — they never go into the code.

---

## Step 1 — Put the code on GitHub

Open a terminal in the project folder (`interactive tutorial builder/`) and run:

```bash
git init
git add .
git status            # ⬅️ sanity check: confirm NO ".env" file is listed
git commit -m "Tuti: initial deploy"
```

> The `.gitignore` already excludes secrets (`.env`), the virtualenv, `node_modules`, build
> output, and run artifacts — so `git status` should **not** show any `.env`. If it does, stop
> and tell me before pushing.

Now create an empty repo on GitHub (github.com → New repository, **don't** add a README),
then connect and push:

```bash
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

---

## Step 2 — Deploy the Backend on Render

Render will read the **`render.yaml`** blueprint that's already in this repo.

1. Go to **render.com → New → Blueprint**.
2. Connect your GitHub account and pick the repo you just pushed.
3. Render detects `render.yaml` and shows a service called **`tuti-backend`**. Click **Apply**.
4. It will ask for the two secret values (they're marked "sync: false"). Paste:
   - **`OPENROUTER_API_KEY`** = your `sk-or-...` key
   - **`SUPABASE_DB_URL`** = your Supabase connection string
5. Click **Create / Deploy**. The first build takes ~5–8 minutes (it builds the Docker image).
6. When it's live, copy the service URL at the top — it looks like:
   **`https://tuti-backend.onrender.com`**
7. Test it: open **`https://tuti-backend.onrender.com/api/health`** in your browser.
   You should see a small JSON health response. ✅

> **Free-tier notes (important):**
> - The backend **sleeps after ~15 min of inactivity**. The next request wakes it and takes
>   ~1 minute (a "cold start"). This is normal on free tier.
> - The free instance has an **ephemeral disk** — generated tutorial files on the server are
>   wiped on restart. Your data (checkpoints, memory, run history) is safe because it lives in
>   **Supabase**. Just **download** a finished tutorial after building it.
> - If builds run out of memory (512 MB on free), upgrade `plan: free` → `plan: starter` in
>   `render.yaml` and push again.

---

## Step 3 — Deploy the Frontend on Vercel

1. Go to **vercel.com → Add New → Project** and import the same GitHub repo.
2. **This is the key setting:** set **Root Directory** to **`frontend`**.
   (Click "Edit" next to Root Directory and choose the `frontend` folder.)
3. Framework should auto-detect as **Vite**. Build command `npm run build`, output `dist` —
   these are already in `frontend/vercel.json`, so leave defaults.
4. Before the first deploy, add **one environment variable** (Settings → Environment Variables):
   - **Name:** `VITE_API_BASE`
   - **Value:** your Render URL from Step 2, e.g. `https://tuti-backend.onrender.com`
     (no trailing slash)
   - Apply it to **Production** (and Preview if you like).
5. Click **Deploy**. After ~1–2 minutes you'll get a URL like **`https://tuti.vercel.app`**.

> `VITE_API_BASE` is baked in at **build time**. If you change it later, you must
> **redeploy** the frontend (Vercel → Deployments → ⋯ → Redeploy) for it to take effect.

---

## Step 4 — Confirm they're talking

1. Open your Vercel URL.
2. Start a small build (upload a short deck).
3. First action may take ~1 min if the Render backend was asleep — that's the cold start.
4. If it connects and streams progress, you're done. 🎉

**Quick way to test the wiring without redeploying:** open your Vercel site with
`?api=` pointing at the backend, e.g.
`https://tuti.vercel.app/?api=https://tuti-backend.onrender.com` — the app honors that
override first, so it's handy for a one-off check.

---

## How updates work from now on

You set `autoDeploy: true`, so:

- **Any code change** → `git add . && git commit -m "..." && git push` →
  Render rebuilds the backend **and** Vercel rebuilds the frontend automatically.
- **Changed the backend URL or a secret?** Update it in the Render/Vercel dashboard.
  Remember: changing `VITE_API_BASE` needs a frontend **redeploy**.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|--------|--------------|-----|
| Frontend loads but "can't reach server" | `VITE_API_BASE` wrong or not redeployed | Fix the value in Vercel → **Redeploy** |
| First request hangs ~1 min then works | Render free-tier cold start | Normal; upgrade plan to avoid |
| Backend deploy fails at build | Out of memory / missing secret | Check Render logs; set `plan: starter`; confirm both secrets are set |
| `/api/health` errors about the database | Supabase URL wrong or schema not run | Re-check `SUPABASE_DB_URL`; run `backend/supabase_schema.sql` in Supabase |
| Generated tutorials disappear after a while | Free-tier ephemeral disk | Download tutorials after building; data itself is safe in Supabase |
| `git status` shows `.env` | gitignore not applied | Stop. Don't push. Ensure you're in the project root; the root `.gitignore` covers `.env` |

---

### Files that make this work (already in the repo)
- **`render.yaml`** (root) — Render blueprint for the backend service
- **`backend/Dockerfile`** — how the backend image is built
- **`backend/.dockerignore`** — keeps secrets/artifacts out of the image
- **`frontend/vercel.json`** — Vercel build config (Vite + SPA routing)
- **`frontend/src/api.js`** — reads `VITE_API_BASE` to find the backend
