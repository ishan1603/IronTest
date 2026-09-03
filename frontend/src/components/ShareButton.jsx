import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { api } from "../lib/api";
import { Button, Spinner } from "./ui";

/** Creates (or revokes) a public link for a completed run and offers export. */
export function ShareButton({ runId, initialToken = null }) {
  const [token, setToken] = useState(initialToken);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  const shareUrl = token ? `${window.location.origin}/r/${token}` : "";

  async function toggle() {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    if (!token) {
      setBusy(true);
      try {
        const { token: t } = await api.shareRun(runId);
        setToken(t);
      } finally {
        setBusy(false);
      }
    }
  }

  async function revoke() {
    setBusy(true);
    try {
      await api.unshareRun(runId);
      setToken(null);
      setOpen(false);
    } finally {
      setBusy(false);
    }
  }

  function copy() {
    navigator.clipboard?.writeText(shareUrl).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  return (
    <div className="relative inline-block">
      <Button variant="secondary" size="sm" onClick={toggle} aria-expanded={open}>
        {token ? "Sharing" : "Share"}
      </Button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.98 }}
            transition={{ duration: 0.14 }}
            className="absolute right-0 z-20 mt-2 w-80 rounded-md border border-line/20 bg-page p-4 shadow-sm"
          >
            {busy && !token ? (
              <div className="flex justify-center py-4">
                <Spinner />
              </div>
            ) : (
              <>
                <p className="text-sm font-medium">Public link</p>
                <p className="mt-1 text-xs text-muted">
                  Anyone with this link sees the results only — no account, repo name, or token.
                </p>
                <div className="mt-3 flex items-center gap-2">
                  <input
                    readOnly
                    value={shareUrl}
                    className="h-9 flex-1 rounded-pill border border-line/20 bg-transparent px-3 font-mono text-xs"
                    onFocus={(e) => e.target.select()}
                  />
                  <Button size="sm" onClick={copy}>
                    {copied ? "Copied" : "Copy"}
                  </Button>
                </div>
                <div className="mt-3 flex items-center justify-between">
                  <a
                    href={token ? api.reportMarkdownUrl(token) : "#"}
                    className="text-xs underline underline-offset-2"
                  >
                    Download Markdown
                  </a>
                  <button onClick={revoke} className="text-xs text-danger underline underline-offset-2">
                    Revoke link
                  </button>
                </div>
              </>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
