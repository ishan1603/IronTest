import { useState } from "react";
import { api } from "../lib/api";
import { Banner, Button, Card, Label, Spinner, Tag } from "./ui";

/** Jira + Azure DevOps connect / disconnect cards for the Integrations page. */
export function TrackerCards({ status, onChange }) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <JiraCard status={status?.jira} onChange={onChange} />
      <AdoCard status={status?.ado} onChange={onChange} />
    </div>
  );
}

function Field({ label, ...props }) {
  return (
    <label className="flex flex-col gap-1">
      <Label>{label}</Label>
      <input
        {...props}
        className="h-9 rounded-md border border-line/20 bg-transparent px-3 text-sm placeholder:text-muted focus:border-line/50"
      />
    </label>
  );
}

function JiraCard({ status, onChange }) {
  const [form, setForm] = useState({ base_url: "", email: "", token: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function connect(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.connectJira(form);
      onChange();
    } catch (exc) {
      setError(exc.message);
    } finally {
      setBusy(false);
    }
  }

  async function disconnect() {
    await api.disconnectJira();
    onChange();
  }

  return (
    <Card className="p-5">
      <div className="flex items-center justify-between">
        <Label>Jira</Label>
        {status?.connected && <Tag tone="success">connected</Tag>}
      </div>

      {status?.connected ? (
        <>
          <p className="mt-3 text-sm">{status.email}</p>
          <p className="font-mono text-xs text-muted">{status.base_url}</p>
          <Button variant="secondary" size="sm" className="mt-3" onClick={disconnect}>
            Disconnect
          </Button>
        </>
      ) : (
        <form onSubmit={connect} className="mt-3 flex flex-col gap-3">
          <Field
            label="Site URL"
            placeholder="https://you.atlassian.net"
            value={form.base_url}
            onChange={(e) => setForm({ ...form, base_url: e.target.value })}
            required
          />
          <Field
            label="Account email"
            type="email"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
            required
          />
          <Field
            label="API token"
            type="password"
            value={form.token}
            onChange={(e) => setForm({ ...form, token: e.target.value })}
            required
          />
          {error && <Banner onDismiss={() => setError("")}>{error}</Banner>}
          <Button type="submit" size="sm" disabled={busy}>
            {busy ? <Spinner className="h-3.5 w-3.5" /> : "Connect Jira"}
          </Button>
          <p className="text-xs text-muted">
            Token from id.atlassian.com → Security → API tokens. Stored encrypted.
          </p>
        </form>
      )}
    </Card>
  );
}

function AdoCard({ status, onChange }) {
  const [form, setForm] = useState({ organization: "", pat: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function connect(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api.connectAdo(form);
      onChange();
    } catch (exc) {
      setError(exc.message);
    } finally {
      setBusy(false);
    }
  }

  async function disconnect() {
    await api.disconnectAdo();
    onChange();
  }

  return (
    <Card className="p-5">
      <div className="flex items-center justify-between">
        <Label>Azure DevOps</Label>
        {status?.connected && <Tag tone="success">connected</Tag>}
      </div>

      {status?.connected ? (
        <>
          <p className="mt-3 font-mono text-sm">dev.azure.com/{status.organization}</p>
          <Button variant="secondary" size="sm" className="mt-3" onClick={disconnect}>
            Disconnect
          </Button>
        </>
      ) : (
        <form onSubmit={connect} className="mt-3 flex flex-col gap-3">
          <Field
            label="Organization"
            placeholder="my-org"
            value={form.organization}
            onChange={(e) => setForm({ ...form, organization: e.target.value })}
            required
          />
          <Field
            label="Personal access token"
            type="password"
            value={form.pat}
            onChange={(e) => setForm({ ...form, pat: e.target.value })}
            required
          />
          {error && <Banner onDismiss={() => setError("")}>{error}</Banner>}
          <Button type="submit" size="sm" disabled={busy}>
            {busy ? <Spinner className="h-3.5 w-3.5" /> : "Connect Azure DevOps"}
          </Button>
          <p className="text-xs text-muted">
            PAT with <span className="font-mono">Work Items (Read)</span>. Stored encrypted.
          </p>
        </form>
      )}
    </Card>
  );
}
