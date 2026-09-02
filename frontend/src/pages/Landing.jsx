import { Navigate } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Button, Label, Spinner } from "../components/ui";

const STEPS = [
  {
    n: "01",
    title: "Connect a repository",
    body: "Sign in with GitHub and pick any repository you can reach, public or private. IronTest only ever reads it.",
  },
  {
    n: "02",
    title: "Describe the work",
    body: "Type the feature you are building, or pull a story straight from Jira or Azure DevOps.",
  },
  {
    n: "03",
    title: "Get tests that actually run",
    body: "Four agents read your code, write tests that import your real modules, and execute them in a sandbox.",
  },
];

export default function Landing() {
  const { status } = useAuth();

  if (status === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner />
      </div>
    );
  }
  if (status === "signed-in") return <Navigate to="/dashboard" replace />;

  return (
    <div className="min-h-screen">
      <header className="mx-auto flex h-14 w-full max-w-[1400px] items-center px-4 sm:px-6">
        <span className="font-mono text-sm font-bold uppercase tracking-[0.18em]">Irontest</span>
      </header>

      <main className="mx-auto w-full max-w-[1400px] px-4 sm:px-6">
        <section className="border-b border-line/15 py-16 sm:py-24">
          <Label>Autonomous QA</Label>
          <h1 className="mt-4 max-w-[16ch] text-3xl font-light leading-[1.05] tracking-tight sm:text-[3.5rem]">
            Tests that <span className="font-semibold">actually run</span> against your code.
          </h1>
          <p className="mt-6 max-w-prose text-base text-muted">
            Point IronTest at a repository and describe what you are building. It reads your modules, writes
            tests that import them for real, runs those tests in a sandbox, and tells you what broke — with
            the pytest output to prove it.
          </p>

          <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center">
            <Button as="a" href={api.loginUrl()} size="lg" className="w-full sm:w-auto">
              <GitHubMark />
              Continue with GitHub
            </Button>
            <span className="text-xs text-muted">Read-only access. Nothing is ever written to your repository.</span>
          </div>
        </section>

        <section className="grid gap-px border-b border-line/15 bg-line/15 sm:grid-cols-3">
          {STEPS.map((step) => (
            <div key={step.n} className="bg-page p-6 sm:p-8">
              <span className="font-mono text-xs text-muted">{step.n}</span>
              <h2 className="mt-3 text-lg font-semibold">{step.title}</h2>
              <p className="mt-2 text-sm text-muted">{step.body}</p>
            </div>
          ))}
        </section>

        <section className="py-16">
          <div className="card-contrast p-8 sm:p-12">
            <Label className="text-contrast-ink/60">The difference</Label>
            <p className="mt-4 max-w-prose text-lg font-light leading-relaxed sm:text-xl">
              A test that cannot fail is not a test. IronTest rejects generated tests that only assert
              literals against themselves, runs the rest in a real sandbox, and reports exactly what
              happened — including when nothing could be measured at all.
            </p>
          </div>
        </section>
      </main>

      <footer className="border-t border-line/15 py-8">
        <div className="mx-auto w-full max-w-[1400px] px-4 text-xs text-muted sm:px-6">
          IronTest — multi-agent QA intelligence.
        </div>
      </footer>
    </div>
  );
}

function GitHubMark() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
    </svg>
  );
}
