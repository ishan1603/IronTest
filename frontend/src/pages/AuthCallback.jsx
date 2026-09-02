import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Banner, Button, Spinner } from "../components/ui";

/** Receives the session token GitHub's callback redirected here with. */
export default function AuthCallback() {
  const [params] = useSearchParams();
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState(params.get("error") || "");
  const handled = useRef(false);

  useEffect(() => {
    if (handled.current) return;
    handled.current = true;

    const token = params.get("token");
    if (!token) {
      setError((current) => current || "GitHub did not return a session. Please try signing in again.");
      return;
    }

    signIn(token)
      // replace: the callback URL holds a token and must not stay in history.
      .then(() => navigate("/dashboard", { replace: true }))
      .catch(() => setError("Could not complete sign-in. Please try again."));
  }, [params, signIn, navigate]);

  if (error) {
    return (
      <div className="mx-auto flex min-h-screen max-w-prose flex-col items-center justify-center gap-6 px-4">
        <Banner tone="danger">{error}</Banner>
        <Button as="a" href={api.loginUrl()}>
          Try again
        </Button>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4">
      <Spinner />
      <p className="text-sm text-muted">Completing sign-in…</p>
    </div>
  );
}
