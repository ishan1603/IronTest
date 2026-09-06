import { Component } from "react";

/**
 * Without this, any render error anywhere unmounts the tree and leaves a blank
 * page with no clue what happened. Shows the error and its component stack so a
 * failure is diagnosable rather than silent.
 */
export class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null, info: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    this.setState({ info });
    // Keep it in the console too, where the stack is clickable.
    console.error("IronTest render error:", error, info?.componentStack);
  }

  render() {
    const { error, info } = this.state;
    if (!error) return this.props.children;

    return (
      <div className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-5 px-6 py-16">
        <p className="label-caps text-danger">Something broke on this screen</p>
        <h1 className="font-display text-2xl font-bold uppercase">
          {error.name || "Error"}
        </h1>
        <p className="text-sm text-muted">
          The rest of IronTest is unaffected. The details below are also in your browser console.
        </p>

        <pre className="scroll-x max-h-40 rounded-md border border-danger/30 p-4 font-mono text-xs text-danger">
          {String(error.message || error)}
        </pre>

        {info?.componentStack && (
          <details className="rounded-md border border-line/15 p-4">
            <summary className="cursor-pointer text-sm">Component stack</summary>
            <pre className="scroll-x mt-3 max-h-64 font-mono text-[11px] leading-relaxed text-muted">
              {info.componentStack.trim()}
            </pre>
          </details>
        )}

        <div className="flex flex-wrap gap-3">
          <button
            onClick={() => this.setState({ error: null, info: null })}
            className="inline-flex h-10 items-center rounded-pill bg-accent px-5 text-sm font-medium text-[#060607]"
          >
            Try again
          </button>
          <a
            href="/dashboard"
            className="inline-flex h-10 items-center rounded-pill border border-line/25 px-5 text-sm"
          >
            Back to repositories
          </a>
        </div>
      </div>
    );
  }
}
