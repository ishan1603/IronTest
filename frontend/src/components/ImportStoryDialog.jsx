import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { Banner, Button, Label, Spinner } from "./ui";

/**
 * Pulls a requirement in from Jira or Azure DevOps.
 *
 * If the tracker is connected (Integrations page), it lists the issues
 * assigned to you and you pick one. Otherwise it falls back to a single
 * issue URL plus credentials, sent for that one fetch and never stored.
 */
export function ImportStoryDialog({ onClose, onImport }) {
  const [status, setStatus] = useState(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const dialog = useRef(null);

  useEffect(() => {
    dialog.current?.focus();
    const onKey = (event) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    api
      .integrations()
      .then(setStatus)
      .catch(() => setStatus(null))
      .finally(() => setStatusLoading(false));
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-0 sm:items-center sm:p-4"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        ref={dialog}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby="import-title"
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-t-md border border-line/15 bg-page p-6 sm:rounded-md"
      >
        <h2 id="import-title" className="text-lg font-semibold">
          Import a requirement
        </h2>

        {statusLoading ? (
          <div className="flex justify-center py-8">
            <Spinner />
          </div>
        ) : (
          <div className="mt-4 flex flex-col gap-6">
            <ConnectedSource
              label="Jira"
              connected={status?.jira?.connected}
              load={api.jiraIssues}
              onPick={onImport}
            />
            <ConnectedSource
              label="Azure DevOps"
              connected={status?.ado?.connected}
              load={api.adoWorkItems}
              onPick={onImport}
            />
            {!status?.jira?.connected && !status?.ado?.connected && (
              <p className="text-xs text-muted">
                Connect Jira or Azure DevOps on the Integrations page to browse your assigned issues
                here. Or paste a single issue below.
              </p>
            )}
            <ManualImport onImport={onImport} />
          </div>
        )}

        <div className="mt-6 flex justify-end">
          <Button variant="secondary" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </div>
  );
}

function ConnectedSource({ label, connected, load, onPick }) {
  const [issues, setIssues] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!connected) return;
    setLoading(true);
    load()
      .then((r) => setIssues(r.issues || []))
      .catch((exc) => setError(exc.message))
      .finally(() => setLoading(false));
  }, [connected, load]);

  if (!connected) return null;

  return (
    <div>
      <Label>{label} — assigned to you</Label>
      {loading ? (
        <div className="py-4">
          <Spinner />
        </div>
      ) : error ? (
        <Banner onDismiss={() => setError("")}>{error}</Banner>
      ) : issues && issues.length === 0 ? (
        <p className="mt-2 text-sm text-muted">Nothing open assigned to you.</p>
      ) : (
        <ul className="mt-2 flex max-h-52 flex-col gap-1 overflow-y-auto">
          {(issues || []).map((issue) => (
            <li key={issue.key}>
              <button
                onClick={() => onPick(issue.requirement)}
                className="w-full rounded-md border border-line/15 px-3 py-2 text-left text-sm hover:border-line/40"
              >
                <span className="font-mono text-xs text-muted">{issue.key}</span>{" "}
                <span>{issue.summary}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ManualImport({ onImport }) {
  const [source, setSource] = useState("jira");
  const [url, setUrl] = useState("");
  const [email, setEmail] = useState("");
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const payload = source === "jira" ? { url, email, token } : { url, pat: token };
      const issue = source === "jira" ? await api.ingestJira(payload) : await api.ingestAzure(payload);
      const text =
        issue.user_story ||
        [issue.summary || issue.title, issue.description || issue.body].filter(Boolean).join("\n\n");
      if (!text.trim()) {
        setError("That item has nothing to import.");
        return;
      }
      onImport(text.trim());
    } catch (exc) {
      setError(exc.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <details className="rounded-md border border-line/15 p-3">
      <summary className="cursor-pointer text-sm">Import from a single issue URL</summary>
      <div className="mt-3">
        <div role="radiogroup" className="inline-flex rounded-pill border border-line/20 p-0.5">
          {[
            ["jira", "Jira"],
            ["azure", "Azure DevOps"],
          ].map(([value, l]) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={source === value}
              onClick={() => setSource(value)}
              className={`rounded-pill px-3 py-1 text-xs ${
                source === value ? "bg-contrast text-contrast-ink" : "text-muted"
              }`}
            >
              {l}
            </button>
          ))}
        </div>

        <form onSubmit={submit} className="mt-3 flex flex-col gap-2">
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            required
            placeholder={source === "jira" ? "https://you.atlassian.net/browse/PROJ-1" : "https://dev.azure.com/org/proj/_workitems/edit/1"}
            className="h-9 rounded-md border border-line/20 bg-transparent px-3 text-sm placeholder:text-muted focus:border-line/50"
          />
          {source === "jira" && (
            <input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              type="email"
              required
              placeholder="account email"
              className="h-9 rounded-md border border-line/20 bg-transparent px-3 text-sm placeholder:text-muted focus:border-line/50"
            />
          )}
          <input
            value={token}
            onChange={(e) => setToken(e.target.value)}
            type="password"
            required
            placeholder={source === "jira" ? "API token" : "personal access token"}
            className="h-9 rounded-md border border-line/20 bg-transparent px-3 text-sm placeholder:text-muted focus:border-line/50"
          />
          {error && <Banner onDismiss={() => setError("")}>{error}</Banner>}
          <Button type="submit" size="sm" disabled={busy}>
            {busy ? <Spinner className="h-3.5 w-3.5" /> : "Import"}
          </Button>
        </form>
      </div>
    </details>
  );
}
