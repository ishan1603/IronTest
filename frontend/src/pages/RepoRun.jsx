import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../lib/api";
import { Shell } from "../components/Shell";
import { Pipeline } from "../components/Pipeline";
import { RunResult } from "../components/RunResult";
import { Banner, Button, Card, Label, Spinner, Tag } from "../components/ui";
import { useRun } from "../hooks/useRun";

/**
 * "Already built" path: no conversation. Pick the repo, hit run, IronTest
 * generates a regression suite for the existing code and executes it.
 *
 * Runs still need a chat row to hang off, so one hidden chat per repo is
 * created and reused. The user never sees it as a conversation.
 */
export default function RepoRun() {
  const { repoId } = useParams();
  const navigate = useNavigate();

  const [repo, setRepo] = useState(null);
  const [chatId, setChatId] = useState(null);
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [focus, setFocus] = useState("");
  const [showFocus, setShowFocus] = useState(false);

  const run = useRun();
  const bottom = useRef(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const repoData = await api.getRepo(repoId);
      setRepo(repoData);

      const { chats } = await api.chats();
      const title = `Test suite · ${repoData.name}`;
      const existing = chats.find(
        (c) => c.repository_id === repoId && c.title === title,
      );
      const chat = existing || (await api.createChat(repoId, title));
      setChatId(chat.id);

      const full = await api.getChat(chat.id);
      setRuns((full.runs || []).slice().reverse());
    } catch (exc) {
      setLoadError(exc.message);
    } finally {
      setLoading(false);
    }
  }, [repoId]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [run.liveRun, run.stages]);

  async function planFeature() {
    const { chats } = await api.chats();
    const featureChat = chats.find(
      (c) => c.repository_id === repoId && !c.title.startsWith("Test suite ·"),
    );
    const chat = featureChat || (await api.createChat(repoId, `Feature · ${repo.name}`));
    navigate(`/chat/${chat.id}`);
  }

  async function startSuite() {
    await run.start(
      { chatId, requirement: focus.trim() || undefined, mode: "existing_code" },
      {
        onComplete: async () => {
          const full = await api.getChat(chatId);
          setRuns((full.runs || []).slice().reverse());
        },
      },
    );
  }

  if (loading) {
    return (
      <Shell>
        <div className="flex justify-center py-24">
          <Spinner />
        </div>
      </Shell>
    );
  }

  if (!repo) {
    return (
      <Shell>
        <div className="px-4 py-16 sm:px-6">
          <Banner>{loadError || "Repository not found."}</Banner>
          <Button as={Link} to="/dashboard" className="mt-4">
            Back to repositories
          </Button>
        </div>
      </Shell>
    );
  }

  const stack = repo.stack_profile || {};
  const latest = run.liveRun?.execution ? run.liveRun : runs[0];

  return (
    <Shell>
      <div className="px-4 py-8 sm:px-6 sm:py-10">
        <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <Label>Test existing code</Label>
            <h1 className="mt-2 truncate text-2xl font-semibold tracking-tight">{repo.full_name}</h1>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {repo.language && <Tag>{repo.language}</Tag>}
              {stack.test_framework && <Tag>{stack.test_framework}</Tag>}
              {stack.has_tests === false && <Tag tone="warning">no existing tests</Tag>}
            </div>
          </div>
          <Button variant="secondary" size="sm" onClick={planFeature} disabled={run.running}>
            Plan a feature instead
          </Button>
        </header>

        {(run.error || loadError) && (
          <div className="mb-6">
            <Banner onDismiss={() => run.setError("")}>{run.error || loadError}</Banner>
          </div>
        )}

        <Card className="mb-8 p-5">
          <p className="text-sm text-muted">
            IronTest reads {repo.full_name}, writes tests that import its real modules, and runs the whole
            suite. A failing test here is a genuine defect in the code as it stands.
          </p>

          {showFocus ? (
            <textarea
              value={focus}
              onChange={(event) => setFocus(event.target.value)}
              rows={2}
              placeholder="Optional: name a module or behaviour to concentrate on."
              aria-label="Optional focus for this run"
              className="mt-3 w-full resize-y rounded-md border border-line/20 bg-transparent px-4 py-3 text-sm placeholder:text-muted focus:border-line/50"
            />
          ) : (
            <button
              onClick={() => setShowFocus(true)}
              className="mt-3 text-xs text-muted underline"
              disabled={run.running}
            >
              Add an optional focus
            </button>
          )}

          <div className="mt-4">
            <Button onClick={startSuite} disabled={run.running || !chatId} size="lg">
              {run.running ? <Spinner className="h-4 w-4" /> : runs.length ? "Run again" : "Generate & run test suite"}
            </Button>
          </div>
        </Card>

        {run.notice && (
          <div className="mb-6">
            <Banner tone="info">{run.notice}</Banner>
          </div>
        )}

        {run.running && (
          <section className="mb-8 animate-fade-up">
            <Pipeline stages={run.stages} message={run.statusMessage} />
            {run.repoContext && <RepoContextPanel context={run.repoContext} />}
          </section>
        )}

        {latest && (
          <section className="mb-10 animate-fade-up">
            <h2 className="label-caps mb-3">{run.running ? "Live result" : "Latest run"}</h2>
            {latest.status === "failed" ? (
              <Banner>{latest.error_message || "This run failed."}</Banner>
            ) : (
              <RunResult run={latest} />
            )}
          </section>
        )}

        {runs.length > 1 && (
          <section>
            <h2 className="label-caps mb-3">Earlier runs</h2>
            <ul className="flex flex-col gap-2">
              {runs.slice(1).map((r) => (
                <li key={r.id} className="card flex flex-wrap items-center gap-3 p-4">
                  <span className="font-mono text-xs text-muted">
                    {new Date(r.created_at).toLocaleString()}
                  </span>
                  <span className="text-sm">
                    {r.passed}/{r.passed + r.failed + r.errors} passed
                  </span>
                  {r.confidence_score != null && (
                    <Tag>confidence {r.confidence_score}</Tag>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )}

        <div ref={bottom} />
      </div>
    </Shell>
  );
}

function RepoContextPanel({ context }) {
  const stack = context.stack || {};
  return (
    <Card className="mt-4 p-4">
      <Label>What IronTest read</Label>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {stack.language && <Tag>{stack.language}</Tag>}
        {stack.test_framework && <Tag>{stack.test_framework}</Tag>}
      </div>
      {context.files_examined?.length > 0 && (
        <ul className="mt-3 space-y-0.5 font-mono text-xs text-muted">
          {context.files_examined.slice(0, 8).map((path) => (
            <li key={path} className="truncate">
              {path}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
