import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { Shell } from "../components/Shell";
import { Banner, Button, Card, EmptyState, Label, Spinner, Tag } from "../components/ui";

export default function Dashboard() {
  const navigate = useNavigate();
  const [connected, setConnected] = useState([]);
  const [available, setAvailable] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [mine, theirs] = await Promise.all([api.connectedRepos(), api.availableRepos()]);
      setConnected(mine.repositories);
      setAvailable(theirs.repositories);
    } catch (exc) {
      setError(exc.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    const unconnected = available.filter((repo) => !repo.connected);
    if (!term) return unconnected;
    return unconnected.filter((repo) => repo.full_name.toLowerCase().includes(term));
  }, [available, query]);

  async function connect(fullName) {
    setBusy(fullName);
    setError("");
    try {
      const repo = await api.connectRepo(fullName);
      const chat = await api.createChat(repo.id);
      navigate(`/chat/${chat.id}`);
    } catch (exc) {
      setError(exc.message);
      setBusy("");
    }
  }

  async function openRepo(repo) {
    setBusy(repo.id);
    try {
      const { chats } = await api.chats();
      const existing = chats.find((chat) => chat.repository_id === repo.id);
      const chat = existing || (await api.createChat(repo.id));
      navigate(`/chat/${chat.id}`);
    } catch (exc) {
      setError(exc.message);
      setBusy("");
    }
  }

  return (
    <Shell>
      <div className="px-4 py-8 sm:px-6 sm:py-10">
        <header className="mb-8">
          <Label>Repositories</Label>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">Choose a repository to test</h1>
          <p className="mt-2 max-w-prose text-sm text-muted">
            Connect a repository, then describe a feature. IronTest reads the code, writes tests that import
            it, and runs them.
          </p>
        </header>

        {error && (
          <div className="mb-6">
            <Banner onDismiss={() => setError("")}>{error}</Banner>
          </div>
        )}

        {loading ? (
          <div className="flex justify-center py-24">
            <Spinner />
          </div>
        ) : (
          <>
            {connected.length > 0 && (
              <section className="mb-10">
                <h2 className="label-caps mb-3">Connected</h2>
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                  {connected.map((repo) => (
                    <RepoCard
                      key={repo.id}
                      repo={repo}
                      connected
                      busy={busy === repo.id}
                      onOpen={() => openRepo(repo)}
                    />
                  ))}
                </div>
              </section>
            )}

            <section>
              <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <h2 className="label-caps">
                  {connected.length > 0 ? "Add another" : "Your GitHub repositories"}
                </h2>
                <input
                  type="search"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search repositories"
                  aria-label="Search repositories"
                  className="h-10 w-full rounded-pill border border-line/20 bg-transparent px-4 text-sm placeholder:text-muted focus:border-line/50 sm:w-72"
                />
              </div>

              {filtered.length === 0 ? (
                <Card className="p-0">
                  <EmptyState
                    title={query ? "No repositories match that search" : "Nothing left to connect"}
                    description={
                      query
                        ? "Try a different name, or check that the repository is visible to your GitHub account."
                        : "Every repository your account can reach is already connected."
                    }
                  />
                </Card>
              ) : (
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                  {filtered.map((repo) => (
                    <RepoCard
                      key={repo.github_repo_id}
                      repo={repo}
                      busy={busy === repo.full_name}
                      onOpen={() => connect(repo.full_name)}
                    />
                  ))}
                </div>
              )}
            </section>
          </>
        )}
      </div>
    </Shell>
  );
}

function RepoCard({ repo, connected = false, busy, onOpen }) {
  const stack = repo.stack_profile || {};

  return (
    <Card className="flex flex-col gap-3 p-4 transition-colors hover:border-line/40">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate font-medium">{repo.name}</p>
          <p className="truncate font-mono text-xs text-muted">{repo.owner}</p>
        </div>
        {repo.private && <Tag>private</Tag>}
      </div>

      {repo.description && <p className="line-clamp-2 text-sm text-muted">{repo.description}</p>}

      <div className="flex flex-wrap items-center gap-1.5">
        {repo.language && <Tag>{repo.language}</Tag>}
        {stack.test_framework && <Tag>{stack.test_framework}</Tag>}
        {connected && stack.has_tests === false && <Tag tone="warning">no tests</Tag>}
      </div>

      <div className="mt-auto flex items-center gap-2 pt-1">
        <Button size="sm" onClick={onOpen} disabled={busy} className="flex-1">
          {busy ? <Spinner className="h-3.5 w-3.5" /> : connected ? "Open" : "Connect"}
        </Button>
        {repo.html_url && (
          <Button
            as="a"
            href={repo.html_url}
            target="_blank"
            rel="noreferrer"
            variant="secondary"
            size="sm"
            aria-label={`Open ${repo.full_name} on GitHub`}
          >
            ↗
          </Button>
        )}
      </div>
    </Card>
  );
}
