import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { Banner, Button, Label, Spinner } from "./ui";

/**
 * Pulls a story from Jira or Azure DevOps into the composer.
 *
 * Credentials are sent per request and never persisted by the browser: they
 * go straight to the API, which uses them for that one fetch.
 */
export function ImportStoryDialog({ onClose, onImport }) {
  const [source, setSource] = useState("jira");
  const [url, setUrl] = useState("");
  const [email, setEmail] = useState("");
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const dialog = useRef(null);

  // Focus trap entry point and Escape-to-close, both expected of a modal.
  useEffect(() => {
    dialog.current?.focus();
    const onKey = (event) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const payload =
        source === "jira" ? { url, email, token } : { url, pat: token };
      const issue = source === "jira" ? await api.ingestJira(payload) : await api.ingestAzure(payload);

      const title = issue.summary || issue.title || "";
      const body = issue.description || issue.body || "";
      const text = [title, body].filter(Boolean).join("\n\n").trim();

      if (!text) {
        setError("That item has no summary or description to import.");
        return;
      }
      onImport(text);
    } catch (exc) {
      setError(exc.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-0 sm:items-center sm:p-4"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
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
          Import a story
        </h2>
        <p className="mt-1 text-sm text-muted">
          Credentials are used for this request only and are never stored in your browser.
        </p>

        <div
          role="radiogroup"
          aria-label="Source"
          className="mt-4 inline-flex rounded-pill border border-line/20 p-0.5"
        >
          {[
            ["jira", "Jira"],
            ["azure", "Azure DevOps"],
          ].map(([value, label]) => (
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
              {label}
            </button>
          ))}
        </div>

        <form onSubmit={submit} className="mt-4 flex flex-col gap-3">
          <Field
            label={source === "jira" ? "Issue URL" : "Work item URL"}
            value={url}
            onChange={setUrl}
            placeholder={
              source === "jira"
                ? "https://you.atlassian.net/browse/PROJ-123"
                : "https://dev.azure.com/org/project/_workitems/edit/123"
            }
            required
          />
          {source === "jira" && (
            <Field label="Account email" type="email" value={email} onChange={setEmail} required />
          )}
          <Field
            label={source === "jira" ? "API token" : "Personal access token"}
            type="password"
            value={token}
            onChange={setToken}
            required
          />

          {error && <Banner onDismiss={() => setError("")}>{error}</Banner>}

          <div className="mt-2 flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? <Spinner className="h-4 w-4" /> : "Import"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

function Field({ label, value, onChange, type = "text", placeholder, required }) {
  return (
    <label className="flex flex-col gap-1">
      <Label>{label}</Label>
      <input
        type={type}
        value={value}
        required={required}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        className="h-10 rounded-md border border-line/20 bg-transparent px-3 text-sm placeholder:text-muted focus:border-line/50"
      />
    </label>
  );
}
