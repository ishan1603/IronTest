import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../lib/api";
import { Shell } from "../components/Shell";
import { RunResult } from "../components/RunResult";
import { ShareButton } from "../components/ShareButton";
import { Banner, Button, Label, Spinner, Tag } from "../components/ui";

/** Read-only view of one stored run, reached from the analytics table. */
export default function RunDetail() {
  const { runId } = useParams();
  const [run, setRun] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .analyticsRun(runId)
      .then(setRun)
      .catch((exc) => setError(exc.message))
      .finally(() => setLoading(false));
  }, [runId]);

  if (loading) {
    return (
      <Shell>
        <div className="flex justify-center py-24">
          <Spinner />
        </div>
      </Shell>
    );
  }

  if (!run) {
    return (
      <Shell>
        <div className="px-4 py-16 sm:px-6">
          <Banner>{error || "Run not found."}</Banner>
          <Button as={Link} to="/runs" className="mt-4">
            Back to analytics
          </Button>
        </div>
      </Shell>
    );
  }

  return (
    <Shell>
      <div className="px-4 py-8 sm:px-6 sm:py-10">
        <Link to="/runs" className="text-xs text-muted underline-offset-2 hover:underline">
          ← All runs
        </Link>
        <header className="mb-6 mt-3">
          <div className="flex flex-wrap items-center gap-2">
            <Label>Run</Label>
            <Tag tone="solid">{run.mode === "specification" ? "Specification" : "Existing code"}</Tag>
            <span className="text-sm text-muted">{new Date(run.created_at).toLocaleString()}</span>
            {run.status === "complete" && (
              <span className="ml-auto">
                <ShareButton runId={run.id} />
              </span>
            )}
          </div>
          <p className="mt-3 max-w-prose text-base">{run.story_text}</p>
        </header>

        {run.status === "failed" ? (
          <Banner>{run.error_message || "This run failed."}</Banner>
        ) : (
          <RunResult run={run} />
        )}

        {run.chat_id && (
          <div className="mt-6">
            <Button as={Link} to={`/chat/${run.chat_id}`} variant="secondary" size="sm">
              Open the conversation
            </Button>
          </div>
        )}
      </div>
    </Shell>
  );
}
