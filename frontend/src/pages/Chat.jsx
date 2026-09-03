import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../lib/api";
import { Shell } from "../components/Shell";
import { Pipeline } from "../components/Pipeline";
import { RunResult } from "../components/RunResult";
import { Banner, Button, Card, Label, Spinner, Tag } from "../components/ui";
import { ImportStoryDialog } from "../components/ImportStoryDialog";
import { useRun } from "../hooks/useRun";

/**
 * "Not built yet" path. Describe a feature you are about to build; the pipeline
 * writes the tests it must pass and flags what to watch out for while building.
 * Mode is fixed to "specification" -- to test code that already exists, use the
 * repository's "Test existing code" page instead.
 */
export default function Chat() {
  const { chatId } = useParams();
  const navigate = useNavigate();

  const [chat, setChat] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [requirement, setRequirement] = useState("");
  const [importing, setImporting] = useState(false);

  const run = useRun();
  const bottom = useRef(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setChat(await api.getChat(chatId));
    } catch (exc) {
      setLoadError(exc.message);
    } finally {
      setLoading(false);
    }
  }, [chatId]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [run.liveRun, run.stages, chat?.runs?.length]);

  async function submit(event) {
    event?.preventDefault();
    const text = requirement.trim();
    if (text.length < 10 || run.running) return;

    await run.start(
      { chatId, requirement: text, mode: "specification" },
      { onComplete: load },
    );
    setRequirement("");
  }

  async function remove() {
    if (!window.confirm("Delete this conversation and its runs?")) return;
    await api.deleteChat(chatId);
    navigate("/dashboard");
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

  if (!chat) {
    return (
      <Shell>
        <div className="px-4 py-16 sm:px-6">
          <Banner>{loadError || "Conversation not found."}</Banner>
          <Button as={Link} to="/dashboard" className="mt-4">
            Back to repositories
          </Button>
        </div>
      </Shell>
    );
  }

  const runs = chat.runs || [];

  return (
    <Shell>
      <div className="flex min-h-[calc(100vh-3.5rem)] flex-col">
        <header className="border-b border-line/15 px-4 py-4 sm:px-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <Label>Plan a feature</Label>
              <h1 className="mt-1 truncate font-mono text-sm font-medium">{chat.repository_full_name}</h1>
            </div>
            <div className="flex items-center gap-2">
              <Button
                as={Link}
                to={`/repo/${chat.repository_id}`}
                variant="secondary"
                size="sm"
              >
                Test existing code
              </Button>
              <Button variant="ghost" size="sm" onClick={remove}>
                Delete
              </Button>
            </div>
          </div>
        </header>

        <div className="flex-1 px-4 py-6 sm:px-6">
          {run.error && (
            <div className="mb-6">
              <Banner onDismiss={() => run.setError("")}>{run.error}</Banner>
            </div>
          )}

          {runs.length === 0 && !run.running && (
            <Card className="mb-6 p-6">
              <h2 className="text-lg font-semibold">Describe what you are about to build</h2>
              <p className="mt-2 max-w-prose text-sm text-muted">
                Write the feature or user story in plain language, or import one from Jira or Azure DevOps.
                IronTest reads {chat.repository_full_name}, writes the tests this feature must pass once it
                exists, and lists what to be careful about while building it. Those tests are expected to
                fail right now — that is the point.
              </p>
            </Card>
          )}

          <div className="flex flex-col gap-8">
            {runs.map((r) => (
              <section key={r.id} className="animate-fade-up">
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  <Tag tone="solid">Specification</Tag>
                  <span className="text-sm text-muted">{new Date(r.created_at).toLocaleString()}</span>
                </div>
                <p className="mb-4 max-w-prose text-base">{r.story_text}</p>
                {r.status === "failed" ? (
                  <Banner>{r.error_message || "This run failed."}</Banner>
                ) : (
                  <RunResult run={r} />
                )}
              </section>
            ))}

            {run.running && (
              <section className="animate-fade-up">
                <Pipeline stages={run.stages} message={run.statusMessage} />
                {run.notice && (
                  <div className="mt-4">
                    <Banner tone="info">{run.notice}</Banner>
                  </div>
                )}
                {run.repoContext && <RepoContextPanel context={run.repoContext} />}
                {run.liveRun?.execution && (
                  <div className="mt-4">
                    <RunResult run={run.liveRun} />
                  </div>
                )}
              </section>
            )}
          </div>

          <div ref={bottom} />
        </div>

        <form
          onSubmit={submit}
          className="sticky bottom-0 border-t border-line/15 bg-page/95 px-4 py-4 backdrop-blur sm:px-6"
        >
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <Tag tone="solid">Specification mode</Tag>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setImporting(true)}
              disabled={run.running}
            >
              Import from Jira / ADO
            </Button>
          </div>

          <div className="flex items-end gap-2">
            <textarea
              value={requirement}
              onChange={(event) => setRequirement(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) submit(event);
              }}
              rows={2}
              disabled={run.running}
              placeholder="As a user, I want to apply a discount code at checkout so that…"
              aria-label="Describe the feature you are planning"
              className="min-h-[44px] flex-1 resize-y rounded-md border border-line/20 bg-transparent px-4 py-3 text-sm placeholder:text-muted focus:border-line/50 disabled:opacity-50"
            />
            <Button type="submit" disabled={run.running || requirement.trim().length < 10} className="h-11">
              {run.running ? <Spinner className="h-4 w-4" /> : "Plan"}
            </Button>
          </div>
          <p className="mt-2 text-xs text-muted">
            IronTest writes the tests this feature must pass and flags what to watch out for while
            building. The tests fail until you build it — that red phase is the spec.
          </p>
        </form>
      </div>

      {importing && (
        <ImportStoryDialog
          onClose={() => setImporting(false)}
          onImport={(text) => {
            setRequirement(text);
            setImporting(false);
          }}
        />
      )}
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
        {stack.has_tests === false && <Tag tone="warning">no existing tests</Tag>}
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
