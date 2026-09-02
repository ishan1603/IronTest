import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, openRunStream } from "../lib/api";
import { Shell } from "../components/Shell";
import { Pipeline } from "../components/Pipeline";
import { RunResult } from "../components/RunResult";
import { Banner, Button, Card, Label, Spinner, Tag } from "../components/ui";
import { ImportStoryDialog } from "../components/ImportStoryDialog";

const IDLE_STAGES = { story: "pending", test: "pending", execution: "pending", defect: "pending" };

export default function Chat() {
  const { chatId } = useParams();
  const navigate = useNavigate();

  const [chat, setChat] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [requirement, setRequirement] = useState("");
  const [mode, setMode] = useState("existing_code");
  const [importing, setImporting] = useState(false);

  const [running, setRunning] = useState(false);
  const [stages, setStages] = useState(IDLE_STAGES);
  const [statusMessage, setStatusMessage] = useState("");
  const [liveRun, setLiveRun] = useState(null);
  const [repoContext, setRepoContext] = useState(null);

  const closeStream = useRef(null);
  const bottom = useRef(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setChat(await api.getChat(chatId));
    } catch (exc) {
      setError(exc.message);
    } finally {
      setLoading(false);
    }
  }, [chatId]);

  useEffect(() => {
    load();
  }, [load]);

  // Always tear the stream down on unmount, or a completed run keeps a
  // connection open behind the user.
  useEffect(() => () => closeStream.current?.(), []);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [liveRun, stages, chat?.runs?.length]);

  async function submit(event) {
    event?.preventDefault();
    const text = requirement.trim();
    if (text.length < 10 || running) return;

    setError("");
    setRunning(true);
    setLiveRun(null);
    setRepoContext(null);
    setStages({ ...IDLE_STAGES, story: "running" });
    setStatusMessage("Starting…");

    try {
      const { session_id } = await api.startRun(chatId, { requirement: text, mode });
      setRequirement("");

      closeStream.current = openRunStream(session_id, {
        onEvent: (event) => handleEvent(event),
        onError: () => {
          setError("Lost connection to the run. Reload to see the stored result.");
          setRunning(false);
        },
      });
    } catch (exc) {
      setError(exc.message);
      setRunning(false);
      setStages(IDLE_STAGES);
    }
  }

  function handleEvent(event) {
    switch (event.event) {
      case "agent_start":
        setStages((prev) => ({ ...prev, [event.agent]: "running" }));
        setStatusMessage(event.message || "");
        break;

      case "repo_context":
        setRepoContext(event);
        break;

      case "agent_complete":
        setStages((prev) => ({ ...prev, [event.agent]: "done" }));
        setLiveRun((prev) => ({
          ...(prev || {}),
          mode,
          ...(event.agent === "story" && { story: event.result }),
          ...(event.agent === "test" && { tests: event.result }),
          ...(event.agent === "execution" && { execution: event.result, backend: event.backend }),
          ...(event.agent === "defect" && { defects: event.result }),
        }));
        break;

      case "pipeline_complete":
        setStatusMessage("");
        setRunning(false);
        closeStream.current?.();
        // Reload so the run is read back from storage rather than held only
        // in memory.
        load();
        break;

      case "error":
        setError(event.message);
        setRunning(false);
        setStages((prev) =>
          Object.fromEntries(
            Object.entries(prev).map(([key, value]) => [key, value === "running" ? "failed" : value]),
          ),
        );
        closeStream.current?.();
        break;

      default:
        break;
    }
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
          <Banner>{error || "Conversation not found."}</Banner>
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
              <Label>Repository</Label>
              <h1 className="mt-1 truncate font-mono text-sm font-medium">
                {chat.repository_full_name}
              </h1>
            </div>
            <Button variant="ghost" size="sm" onClick={remove}>
              Delete
            </Button>
          </div>
        </header>

        <div className="flex-1 px-4 py-6 sm:px-6">
          {error && (
            <div className="mb-6">
              <Banner onDismiss={() => setError("")}>{error}</Banner>
            </div>
          )}

          {runs.length === 0 && !running && (
            <Card className="mb-6 p-6">
              <h2 className="text-lg font-semibold">Describe what you are building</h2>
              <p className="mt-2 max-w-prose text-sm text-muted">
                Write a feature or user story in plain language, or import one from Jira or Azure DevOps.
                IronTest reads {chat.repository_full_name}, writes tests that import its modules, and runs
                them in a sandbox.
              </p>
            </Card>
          )}

          <div className="flex flex-col gap-8">
            {runs.map((run) => (
              <section key={run.id} className="animate-fade-up">
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  <Tag tone="solid">{run.mode === "specification" ? "Specification" : "Existing code"}</Tag>
                  <span className="text-sm text-muted">{new Date(run.created_at).toLocaleString()}</span>
                </div>
                <p className="mb-4 max-w-prose text-base">{run.story_text}</p>
                {run.status === "failed" ? (
                  <Banner>{run.error_message || "This run failed."}</Banner>
                ) : (
                  <RunResult run={run} />
                )}
              </section>
            ))}

            {running && (
              <section className="animate-fade-up">
                <Pipeline stages={stages} message={statusMessage} />
                {repoContext && <RepoContextPanel context={repoContext} />}
                {liveRun?.execution && (
                  <div className="mt-4">
                    <RunResult run={liveRun} />
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
            <ModeToggle mode={mode} onChange={setMode} disabled={running} />
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setImporting(true)}
              disabled={running}
            >
              Import from Jira / ADO
            </Button>
          </div>

          <div className="flex items-end gap-2">
            <textarea
              value={requirement}
              onChange={(event) => setRequirement(event.target.value)}
              onKeyDown={(event) => {
                // Enter submits; Shift+Enter adds a line, as in most chat UIs.
                if (event.key === "Enter" && !event.shiftKey) submit(event);
              }}
              rows={2}
              disabled={running}
              placeholder="As a user, I want to apply a discount code at checkout so that…"
              aria-label="Describe the feature to test"
              className="min-h-[44px] flex-1 resize-y rounded-md border border-line/20 bg-transparent px-4 py-3 text-sm placeholder:text-muted focus:border-line/50 disabled:opacity-50"
            />
            <Button type="submit" disabled={running || requirement.trim().length < 10} className="h-11">
              {running ? <Spinner className="h-4 w-4" /> : "Run"}
            </Button>
          </div>
          <p className="mt-2 text-xs text-muted">
            {mode === "specification"
              ? "Specification mode: tests are expected to fail until you build the feature."
              : "Existing code mode: tests should pass; a failure is a real defect."}
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

function ModeToggle({ mode, onChange, disabled }) {
  const options = [
    ["existing_code", "Already built"],
    ["specification", "Not built yet"],
  ];
  return (
    <div role="radiogroup" aria-label="Run mode" className="inline-flex rounded-pill border border-line/20 p-0.5">
      {options.map(([value, label]) => (
        <button
          key={value}
          type="button"
          role="radio"
          aria-checked={mode === value}
          disabled={disabled}
          onClick={() => onChange(value)}
          className={`rounded-pill px-3 py-1 text-xs transition-colors disabled:opacity-50 ${
            mode === value ? "bg-contrast text-contrast-ink" : "text-muted hover:text-ink"
          }`}
        >
          {label}
        </button>
      ))}
    </div>
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
