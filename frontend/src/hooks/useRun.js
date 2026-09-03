import { useCallback, useEffect, useRef, useState } from "react";
import { api, openRunStream } from "../lib/api";

export const IDLE_STAGES = { story: "pending", test: "pending", execution: "pending", defect: "pending" };

/**
 * Drives one pipeline run over SSE. Shared by the repo-run page (no chat) and
 * the feature-planning chat, so the event handling lives in one place.
 */
export function useRun() {
  const [running, setRunning] = useState(false);
  const [stages, setStages] = useState(IDLE_STAGES);
  const [statusMessage, setStatusMessage] = useState("");
  const [liveRun, setLiveRun] = useState(null);
  const [repoContext, setRepoContext] = useState(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const closeStream = useRef(null);
  const onComplete = useRef(null);

  // Tear the stream down on unmount so a finished run does not leave a socket
  // open behind the user.
  useEffect(() => () => closeStream.current?.(), []);

  const handleEvent = useCallback((event, mode) => {
    switch (event.event) {
      case "agent_start":
        setStages((prev) => ({ ...prev, [event.agent]: "running" }));
        setStatusMessage(event.message || "");
        break;
      case "runner_notice":
        setNotice(event.message || "");
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
          ...(event.agent === "execution" && {
            execution: event.result,
            backend: event.backend,
            sandboxed: event.sandboxed,
          }),
          ...(event.agent === "defect" && { defects: event.result }),
        }));
        break;
      case "pipeline_complete":
        setStatusMessage("");
        setRunning(false);
        closeStream.current?.();
        onComplete.current?.();
        break;
      case "error":
        setError(event.message);
        setRunning(false);
        setStages((prev) =>
          Object.fromEntries(
            Object.entries(prev).map(([k, v]) => [k, v === "running" ? "failed" : v]),
          ),
        );
        closeStream.current?.();
        break;
      default:
        break;
    }
  }, []);

  const start = useCallback(
    async ({ chatId, requirement, mode }, { onComplete: done } = {}) => {
      onComplete.current = done || null;
      setError("");
      setNotice("");
      setRunning(true);
      setLiveRun(null);
      setRepoContext(null);
      setStages({ ...IDLE_STAGES, story: "running" });
      setStatusMessage("Starting…");

      try {
        const { session_id } = await api.startRun(chatId, { requirement, mode });
        closeStream.current = openRunStream(session_id, {
          onEvent: (event) => handleEvent(event, mode),
          onError: () => {
            setError("Lost connection to the run. Reload the page to see the stored result.");
            setRunning(false);
          },
        });
      } catch (exc) {
        setError(exc.message);
        setRunning(false);
        setStages(IDLE_STAGES);
      }
    },
    [handleEvent],
  );

  return { running, stages, statusMessage, liveRun, repoContext, notice, error, setError, start };
}
