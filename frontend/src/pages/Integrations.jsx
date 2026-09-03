import { useEffect, useState } from "react";
import { API_BASE, api } from "../lib/api";
import { Shell } from "../components/Shell";
import { Banner, Button, Card, Label, Spinner } from "../components/ui";
import { TrackerCards } from "../components/TrackerCards";

const WORKFLOW = `name: IronTest PR gate

on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  irontest:
    runs-on: ubuntu-latest
    steps:
      - name: Trigger IronTest
        env:
          KEY: \${{ secrets.IRONTEST_API_KEY }}
          BASE: \${{ secrets.IRONTEST_API_BASE }}
          REPO: \${{ github.repository }}
          HEAD: \${{ github.head_ref }}
          TARGET: \${{ github.base_ref }}
          PR: \${{ github.event.number }}
        run: |
          curl --fail --silent --show-error -X POST "$BASE/api/ci/run" \\
            -H "X-IronTest-Key: $KEY" -H "Content-Type: application/json" \\
            -d "{\\"repository\\":\\"$REPO\\",\\"head_ref\\":\\"$HEAD\\",\\"base_ref\\":\\"$TARGET\\",\\"pr_number\\":$PR}"
`;

export default function Integrations() {
  const [apiKey, setApiKey] = useState(null);
  const [trackers, setTrackers] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState("");

  useEffect(() => {
    Promise.all([api.getApiKey(), api.integrations()])
      .then(([k, tr]) => {
        setApiKey(k.api_key);
        setTrackers(tr);
      })
      .catch((exc) => setError(exc.message))
      .finally(() => setLoading(false));
  }, []);

  async function rotate() {
    setBusy(true);
    setError("");
    try {
      const { api_key } = await api.rotateApiKey();
      setApiKey(api_key);
    } catch (exc) {
      setError(exc.message);
    } finally {
      setBusy(false);
    }
  }

  function copy(text, which) {
    navigator.clipboard?.writeText(text).then(() => {
      setCopied(which);
      setTimeout(() => setCopied(""), 1500);
    });
  }

  const reloadTrackers = () => api.integrations().then(setTrackers).catch(() => {});

  return (
    <Shell>
      <div className="px-4 py-8 sm:px-6 sm:py-10">
        <header className="mb-8">
          <Label>Integrations</Label>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">Trackers, CI &amp; API</h1>
          <p className="mt-2 max-w-prose text-sm text-muted">
            Run IronTest on every pull request. It generates a suite against the PR branch, runs it,
            and posts the verdict as a comment.
          </p>
        </header>

        {error && (
          <div className="mb-6">
            <Banner onDismiss={() => setError("")}>{error}</Banner>
          </div>
        )}

        {loading ? (
          <div className="flex justify-center py-16">
            <Spinner />
          </div>
        ) : (
          <div className="flex flex-col gap-6">
            <section>
              <h2 className="label-caps mb-3">Issue trackers</h2>
              <TrackerCards status={trackers} onChange={reloadTrackers} />
            </section>

            <Card className="p-5">
              <Label>Your API key</Label>
              <p className="mt-1 text-xs text-muted">
                Used in the <code>X-IronTest-Key</code> header. Treat it like a password.
              </p>
              {apiKey ? (
                <div className="mt-3 flex items-center gap-2">
                  <input
                    readOnly
                    value={apiKey}
                    onFocus={(e) => e.target.select()}
                    className="h-9 flex-1 rounded-pill border border-line/20 bg-transparent px-3 font-mono text-xs"
                  />
                  <Button size="sm" onClick={() => copy(apiKey, "key")}>
                    {copied === "key" ? "Copied" : "Copy"}
                  </Button>
                </div>
              ) : (
                <p className="mt-3 text-sm text-muted">No key yet.</p>
              )}
              <div className="mt-3">
                <Button size="sm" variant="secondary" onClick={rotate} disabled={busy}>
                  {busy ? <Spinner className="h-3.5 w-3.5" /> : apiKey ? "Rotate key" : "Generate key"}
                </Button>
              </div>
            </Card>

            <Card className="p-5">
              <Label>Repo secrets</Label>
              <p className="mt-1 text-xs text-muted">
                Add these to the repository under Settings → Secrets and variables → Actions.
              </p>
              <dl className="mt-3 grid gap-2 font-mono text-xs">
                <div className="flex items-center justify-between gap-2">
                  <dt>IRONTEST_API_KEY</dt>
                  <dd className="text-muted">your key above</dd>
                </div>
                <div className="flex items-center justify-between gap-2">
                  <dt>IRONTEST_API_BASE</dt>
                  <dd>
                    <button className="underline" onClick={() => copy(API_BASE, "base")}>
                      {copied === "base" ? "Copied" : API_BASE}
                    </button>
                  </dd>
                </div>
              </dl>
            </Card>

            <Card className="p-5">
              <div className="flex items-center justify-between">
                <Label>Workflow file</Label>
                <Button size="sm" onClick={() => copy(WORKFLOW, "wf")}>
                  {copied === "wf" ? "Copied" : "Copy"}
                </Button>
              </div>
              <p className="mt-1 text-xs text-muted">
                Commit as <code>.github/workflows/irontest.yml</code> in any repository you have connected.
              </p>
              <pre className="scroll-x mt-3 max-h-80 rounded-sm border border-line/12 p-3 font-mono text-xs leading-relaxed">
                {WORKFLOW}
              </pre>
            </Card>
          </div>
        )}
      </div>
    </Shell>
  );
}
