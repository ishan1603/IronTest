# Security

## Trust boundaries

| Input | Trust | Handling |
| --- | --- | --- |
| A user's repository | **None** | Cloned and executed only inside a sandbox |
| LLM output | **None** | Parsed, validated, never `eval`'d; snippets run only in a sandbox |
| Jira / ADO credentials | Per request | Forwarded for one fetch, never persisted |
| GitHub OAuth token | Secret | Fernet-encrypted at rest, never returned by the API |
| Session token | Bearer | Signed JWT, checked on every request |

## Executing untrusted code

The central risk: generated tests import the target repository's real modules,
so a run executes third-party code plus whatever its dependency install runs.

**It never executes on the API host.** `runners/select_runner()` returns a
sandbox or nothing, and a repository run with no sandbox fails rather than
degrading to local execution.

**Docker backend.** No swap (so the memory ceiling is real), `--cap-drop ALL`,
`--security-opt no-new-privileges`, a pid limit, CPU and memory caps, and a
wall-clock timeout. The clone credential is written to a git credentials file
inside the container rather than passed on a command line, where it would be
visible in the process list and in captured output.

**GitHub Actions backend.** Execution happens in GitHub's own isolated runners,
inside a dedicated dispatch repository. Repositories under test are only ever
cloned. The workflow refuses to write payload files outside the checkout.

> The dispatch token is powerful: anyone who can dispatch that workflow can run
> arbitrary code in your Actions account. Keep the runner repository private.

## Authentication

Sessions are signed JWTs, so the API stays stateless across the multiple
workers a free-tier host may run. OAuth state is a short-lived signed token
rather than server-side storage, which keeps CSRF protection working across
restarts and workers.

GitHub tokens are encrypted with Fernet under a key derived from `SECRET_KEY`.
A rotated key makes stored tokens undecryptable, which reads as *signed out*
and forces a re-login rather than surfacing corrupt credentials.

Requested scopes are `read:user user:email repo` — read access only. IronTest
never writes to a user's repository.

## Authorization

Every data route depends on `current_user`, so an unauthenticated request is
rejected before any handler runs. Resources belonging to another account return
**404, not 403**, so a foreign id is indistinguishable from a wrong one.

History, module statistics, and learning context are all scoped by `user_id`.
[Tests assert this](../backend/tests/test_auth_and_scoping.py) rather than
leaving it to convention.

## Transport

CORS origins come from configuration. The previous build used
`allow_origins=["*"]` together with `allow_credentials=True` — a combination
browsers reject outright, and which would have exposed the API to every origin
had it been honoured.

SSE streams carry their token as a query parameter, because `EventSource`
cannot set headers. The token is verified and checked against the session's
recorded owner, so a leaked session id is not on its own sufficient to read a
stream.

## Known limitations

- **Session revocation.** Signing out clears the stored GitHub token, which
  revokes this server's access to your code, but the JWT stays valid until it
  expires. A token denylist would be needed for immediate revocation.
- **No rate limiting.** A signed-in user can start unlimited runs. Free-tier
  provider and Actions quotas are the practical ceiling.
- **`create_all` is not a migration tool.** It adds missing tables; it will not
  alter an existing column.
- **Docker socket in compose.** `docker-compose.yml` mounts the host socket so
  the API can drive the sandbox. That grants the container control of your
  daemon — local development only.

## Reporting

Open a private security advisory on the repository rather than a public issue.
