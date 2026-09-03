import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { Shell } from "../components/Shell";
import { Banner, Card, EmptyState, Label, Spinner, Tag } from "../components/ui";

export default function Runs() {
  const [chats, setChats] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .chats()
      // Hide the per-repo suite chats the "Test existing code" page uses
      // internally; they are runs, not conversations.
      .then((data) => setChats(data.chats.filter((c) => !c.title.startsWith("Test suite ·"))))
      .catch((exc) => setError(exc.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <Shell>
      <div className="px-4 py-8 sm:px-6 sm:py-10">
        <Label>History</Label>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">Conversations</h1>

        {error && (
          <div className="mt-6">
            <Banner onDismiss={() => setError("")}>{error}</Banner>
          </div>
        )}

        {loading ? (
          <div className="flex justify-center py-24">
            <Spinner />
          </div>
        ) : chats.length === 0 ? (
          <Card className="mt-6 p-0">
            <EmptyState
              title="No conversations yet"
              description="Connect a repository and describe a feature to start your first run."
              action={
                <Link to="/dashboard" className="rounded-pill bg-contrast px-4 py-2 text-sm text-contrast-ink">
                  Choose a repository
                </Link>
              }
            />
          </Card>
        ) : (
          <ul className="mt-6 flex flex-col gap-2">
            {chats.map((chat) => (
              <li key={chat.id}>
                <Link
                  to={`/chat/${chat.id}`}
                  className="card flex items-center gap-4 p-4 transition-colors hover:border-line/40"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{chat.title}</p>
                    <p className="truncate font-mono text-xs text-muted">{chat.repository_full_name}</p>
                  </div>
                  <Tag>{new Date(chat.updated_at).toLocaleDateString()}</Tag>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Shell>
  );
}
