# Deployment

Frontend on Vercel, API and Postgres on Render, tests on GitHub Actions.
Every piece is free tier.

## The constraint that shapes this

Generated tests import the target repository's real code, so running them means
executing arbitrary third-party code. That cannot happen on the API host: it is
a security problem and a resource problem. Locally the sandbox is Docker.

Render's free tier has no Docker-in-Docker, so **a deployed install must use
the GitHub Actions backend.** That is step 1 below, and skipping it leaves
repository runs unable to execute.

---

## 1. The test runner repository

Tests run in a dedicated repository, not in the ones being tested. Users' repos
are only ever cloned.

1. Create a new **private, empty** repository, e.g. `you/irontest-runner`.
2. Copy [`deploy/irontest-runner.yml`](../deploy/irontest-runner.yml) into it at
   `.github/workflows/irontest-runner.yml` and push to `main`.
3. Create a fine-grained personal access token scoped to **only that repository**
   with **Actions: read and write**.

> Anyone who can dispatch this workflow can run arbitrary code in your Actions
> account. Keep the repository private and treat the token as a secret.

You now have `ACTIONS_RUNNER_REPO=you/irontest-runner` and
`ACTIONS_DISPATCH_TOKEN=<token>`.

## 2. GitHub OAuth app

[github.com/settings/developers](https://github.com/settings/developers) → **New OAuth App**

| Field | Value |
| --- | --- |
| Homepage URL | `https://your-app.vercel.app` |
| Authorization callback URL | `https://your-api.onrender.com/api/auth/github/callback` |

The callback must match `GITHUB_CALLBACK_URL` **exactly** — a trailing slash
difference is enough to fail the exchange.

## 3. API on Render

Point Render at [`deploy/render.yaml`](../deploy/render.yaml), or create a Web
Service manually with root directory `backend`, build `pip install -r
requirements.txt`, start `uvicorn main:app --host 0.0.0.0 --port $PORT`.

Set these in the dashboard:

```
ENVIRONMENT=production
SECRET_KEY=<generate: python -c "import secrets; print(secrets.token_urlsafe(48))">
DATABASE_URL=<from the Render Postgres instance>

GITHUB_CLIENT_ID=...
GITHUB_CLIENT_SECRET=...
GITHUB_CALLBACK_URL=https://your-api.onrender.com/api/auth/github/callback
FRONTEND_URL=https://your-app.vercel.app

GROQ_API_KEY=...
GEMINI_API_KEY=...

TEST_RUNNER=github_actions
ACTIONS_RUNNER_REPO=you/irontest-runner
ACTIONS_DISPATCH_TOKEN=...
```

`SECRET_KEY` must be stable. It signs sessions and derives the key that
encrypts stored GitHub tokens, so rotating it logs everyone out and discards
those stored tokens.

`DATABASE_URL` is normalised automatically — Render hands out `postgres://`,
which SQLAlchemy 2 rejects.

## 4. Frontend on Vercel

Import the repository, set root directory to `frontend`. The framework preset
and build settings come from [`frontend/vercel.json`](../frontend/vercel.json).

One environment variable:

```
VITE_API_BASE=https://your-api.onrender.com
```

It is read at **build** time, so change it and redeploy — editing it alone does
nothing to the running site.

## 5. Verify

```bash
curl https://your-api.onrender.com/health
```

Expect `"status": "ok"`, at least one provider with `"active": true`, and
`"test_runner": {"selected": "github_actions"}`. If `selected` is `null`,
step 1 is incomplete and repository runs will fail.

Then sign in on the Vercel URL, connect a repository, and run something.

---

## Free-tier limits worth knowing

| Limit | Consequence |
| --- | --- |
| Render free services sleep after ~15 min idle | First request takes ~30s. Wake it before a demo. |
| Render free Postgres expires after 90 days | Back up or recreate. |
| Actions: 2,000 min/month private, unlimited public | A run is 1–3 min. |
| Groq / Gemini free tiers rate-limit per minute and per day | Configure both; the chain fails over automatically. |

## Troubleshooting

**Sign-in redirects to an error.** `GITHUB_CALLBACK_URL` and the OAuth app's
callback differ, or `FRONTEND_URL` is wrong so the post-login redirect lands
nowhere.

**Browser console shows a CORS failure.** `FRONTEND_URL` does not match the
Vercel origin. Add extra origins with `EXTRA_CORS_ORIGINS` (comma separated) —
preview deployments each get their own hostname.

**Runs fail with "No test sandbox is available."** `TEST_RUNNER=github_actions`
but the runner repo or dispatch token is missing or wrong. Check `/health`.

**"The workflow finished but produced no JUnit report."** The repository's
detected test command did not emit `results.xml`. Check the Actions run log in
the dispatch repository; the detected commands are visible in the run's
`repo_context` event and on the repository card.
