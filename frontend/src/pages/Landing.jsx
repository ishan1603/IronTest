import { useEffect, useRef, useState } from "react";
import { Navigate } from "react-router-dom";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Spinner } from "../components/ui";
import { HeroAnimation } from "../components/HeroAnimation";
import { Brackets, Marquee, StepMeter, Tick, TickField, TickStrip } from "../components/motifs";
import { PipelineVisual } from "../components/PipelineVisual";

const STEPS = [
  {
    n: 1,
    title: "I READ YOUR CODE",
    body: "Your modules, their real signatures, the tests you already have. Not a summary of your repo, but the actual symbols a test can import.",
  },
  {
    n: 2,
    title: "I WRITE THE TESTS",
    body: "Cases that import your real functions and call them. A test that only asserts a literal against itself is rejected before it ever runs.",
  },
  {
    n: 3,
    title: "I RUN THEM FOR REAL",
    body: "In a sandbox, against a fresh checkout. Whatever pytest says is what you see. No shaping, no sampling, no invented tracebacks.",
  },
  {
    n: 4,
    title: "I TELL YOU WHAT BROKE",
    body: "Per-module risk, a release verdict, and a concrete fix for each failure, with the runner's own output as the evidence.",
  },
];

const PROMISES = [
  ["01", "Never shaped", "A fully passing suite reports as fully passing. There is no target band."],
  ["02", "Never invented", "No parseable report means the run failed, with its logs attached."],
  ["03", "Never shared", "History, risk and trends are scoped to your account alone."],
];

const TICKER = [
  "Real execution",
  "Regression gate",
  "Fix suggestions",
  "Flaky detection",
  "Shareable reports",
  "CI gate",
];

export default function Landing() {
  const { status } = useAuth();
  const root = useRef(null);
  const [activeStep, setActiveStep] = useState(1);

  useEffect(() => {
    if (status !== "signed-out") return undefined;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return undefined;

    let ctx;
    let cancelled = false;

    // GSAP is imported only here, so signed-in users never download it.
    (async () => {
      const [{ gsap }, { ScrollTrigger }] = await Promise.all([
        import("gsap"),
        import("gsap/ScrollTrigger"),
      ]);
      if (cancelled) return;
      gsap.registerPlugin(ScrollTrigger);

      ctx = gsap.context((self) => {
        const mm = gsap.matchMedia();

        self.selector("[data-reveal-words]").forEach((el) => {
          gsap.fromTo(
            el.querySelectorAll("span[data-w]"),
            { opacity: 0.14 },
            {
              opacity: 1,
              stagger: 0.08,
              ease: "none",
              scrollTrigger: { trigger: el, start: "top 78%", end: "bottom 55%", scrub: true },
            },
          );
        });

        self.selector("[data-rise]").forEach((el) => {
          gsap.from(el, {
            y: 40,
            opacity: 0,
            duration: 0.8,
            ease: "power3.out",
            // Without clearProps the tween leaves inline opacity behind, which
            // outranks the Tailwind class that drives the active-step state.
            clearProps: "opacity,transform",
            scrollTrigger: { trigger: el, start: "top 88%" },
          });
        });

        // Desktop only: parallax and pinning. Pinning on a phone fights native
        // scrolling and is the main source of jank.
        mm.add("(min-width: 1024px)", () => {
          gsap.to("[data-hero-mark]", {
            yPercent: -38,
            ease: "none",
            scrollTrigger: { trigger: "[data-hero]", start: "top top", end: "bottom top", scrub: 0.4 },
          });
          gsap.to("[data-hero-panel]", {
            yPercent: 12,
            scale: 0.94,
            ease: "none",
            scrollTrigger: { trigger: "[data-hero]", start: "top top", end: "bottom top", scrub: 0.4 },
          });

          ScrollTrigger.create({
            trigger: "[data-steps]",
            start: "top top",
            end: "+=280%",
            pin: "[data-steps-inner]",
            scrub: true,
            onUpdate: (t) => {
              setActiveStep(Math.min(STEPS.length, Math.floor(t.progress * STEPS.length) + 1));
            },
          });
        });

        gsap.from("[data-footer-mark]", {
          scale: 0.86,
          opacity: 0,
          duration: 1,
          ease: "power3.out",
          scrollTrigger: { trigger: "[data-footer-mark]", start: "top 92%" },
        });
      }, root);
    })();

    return () => {
      cancelled = true;
      ctx?.revert();
    };
  }, [status]);

  if (status === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner />
      </div>
    );
  }
  if (status === "signed-in") return <Navigate to="/dashboard" replace />;

  return (
    <div ref={root} className="overflow-x-hidden">
      <Nav />

      <section data-hero className="relative min-h-[92vh] overflow-hidden pt-20 sm:pt-24">
        <TickField />

        <h1
          data-hero-mark
          aria-label="IronTest"
          className="display gpu pointer-events-none select-none text-giga leading-none text-ink/95"
          style={{ marginTop: "-0.14em", marginLeft: "-0.04em" }}
        >
          IRONTEST
        </h1>

        <div className="mx-auto -mt-4 flex w-full max-w-shell flex-col gap-6 px-4 sm:px-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <p className="label-caps max-w-[22ch]">Tests that import your real code</p>
            <p className="label-caps max-w-[22ch] sm:text-right">No fabricated results</p>
          </div>

          <div data-hero-panel className="gpu relative mx-auto w-full max-w-3xl">
            <Brackets inset={-10} />
            <HeroAnimation />
          </div>

          <div className="flex flex-col items-center gap-4">
            <AccentCta />
            <p className="text-xs text-muted">
              Read-only access. Nothing is ever written to your repository.
            </p>
          </div>
        </div>

        <TickStrip count={90} className="mt-10 w-full justify-center opacity-70" />
      </section>

      <section className="border-t border-line/10 px-4 py-24 sm:px-6 sm:py-32">
        <div className="mx-auto max-w-shell">
          <RevealWords
            className="display text-mega text-ink"
            text="Most AI test tools generate code that looks right. IronTest runs it against your repository and shows you the output."
          />
        </div>
      </section>

      <section data-invert="true" className="relative overflow-hidden bg-page py-24 sm:py-32">
        <span
          aria-hidden="true"
          className="display pointer-events-none absolute -left-6 top-6 select-none text-giga leading-none text-ink/[0.05]"
        >
          QA
        </span>
        <div className="relative mx-auto max-w-shell px-4 sm:px-6">
          <p data-rise className="label-caps">
            The difference
          </p>
          <RevealWords
            className="display mt-6 max-w-[18ch] text-mega text-ink"
            text="A test that cannot fail is not a test."
          />
          <p data-rise className="mt-8 max-w-prose text-base text-muted">
            IronTest rejects generated tests that only assert a literal against themselves, runs the rest in
            a real sandbox, and reports exactly what happened, including when nothing could be measured at
            all. Absence of evidence is never reported as success.
          </p>
          <div data-rise className="mt-10 grid gap-px overflow-hidden rounded-lg bg-line/15 sm:grid-cols-3">
            {PROMISES.map(([n, title, body]) => (
              <div key={n} className="bg-page p-6">
                <span className="font-mono text-xs text-accent">{n}</span>
                <h3 className="mt-3 font-display text-lg font-bold uppercase">{title}</h3>
                <p className="mt-2 text-sm text-muted">{body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section data-steps className="relative">
        <div data-steps-inner className="min-h-screen border-t border-line/10">
          <div className="mx-auto grid max-w-shell gap-10 px-4 py-16 sm:px-6 lg:grid-cols-2 lg:items-center lg:gap-16 lg:py-24">
            <div className="relative order-2 flex flex-col gap-6 lg:order-1">
              <TickField className="hidden lg:block" />
              <PipelineVisual step={activeStep} className="relative" />
              <StepMeter step={activeStep} total={STEPS.length} className="relative" />
            </div>

            <div className="order-1 lg:order-2">
              <p className="label-caps">The pipeline</p>
              <ol className="mt-6 flex flex-col gap-10 lg:gap-14">
                {STEPS.map((step) => (
                  <li
                    key={step.n}
                    data-step
                    className={
                      "transition-opacity duration-500 " +
                      (step.n === activeStep ? "opacity-100" : "opacity-100 lg:opacity-30")
                    }
                  >
                    <div className="flex items-center gap-3">
                      <Tick height={18} />
                      <span className="font-mono text-xs text-accent">
                        {String(step.n).padStart(2, "0")}
                      </span>
                    </div>
                    <h3 className="display mt-3 text-2xl">{step.title}</h3>
                    <p className="mt-3 max-w-prose text-sm text-muted sm:text-base">{step.body}</p>
                  </li>
                ))}
              </ol>
            </div>
          </div>
        </div>
      </section>

      <div className="border-y border-line/10 py-5">
        <Marquee
          className="font-display text-lg uppercase tracking-wide text-muted"
          items={TICKER}
        />
      </div>

      <footer className="relative overflow-hidden px-4 pt-20 sm:px-6 sm:pt-28">
        <div className="mx-auto max-w-shell">
          <div data-rise className="bracketed relative p-8 sm:p-14">
            <RevealWords className="display max-w-[16ch] text-mega" text="Point it at a repository." />
            <div className="mt-8">
              <AccentCta />
            </div>
          </div>

          <h2
            data-footer-mark
            aria-hidden="true"
            className="display gpu mt-16 select-none text-giga leading-none text-ink"
          >
            IRONTEST
          </h2>

          <div className="flex flex-col gap-4 border-t border-line/10 py-8 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs text-muted">Multi-agent QA intelligence. Built by Team 838.</p>
            <TickStrip count={30} className="opacity-60" />
          </div>
        </div>
      </footer>
    </div>
  );
}

function AccentCta() {
  return (
    <a
      href={api.loginUrl()}
      className="inline-flex h-12 items-center gap-3 rounded-pill bg-accent px-7 font-medium text-[#060607] transition-transform duration-200 hover:scale-[1.03] active:scale-95"
    >
      <GitHubMark />
      Continue with GitHub
    </a>
  );
}

/** Splits text into words so GSAP can fade them in one at a time. */
function RevealWords({ text, className }) {
  return (
    <p data-reveal-words className={className}>
      {text.split(" ").map((word, index) => (
        <span key={index} data-w className="inline-block">
          {word}
          {" "}
        </span>
      ))}
    </p>
  );
}

function Nav() {
  return (
    <header className="fixed inset-x-0 top-0 z-40 border-b border-line/10 bg-page/70 backdrop-blur-md">
      <div className="mx-auto flex h-16 w-full max-w-shell items-center justify-between px-4 sm:px-6">
        <span className="font-display text-lg font-bold uppercase tracking-[0.1em]">Irontest</span>
        <nav className="flex items-center gap-2">
          <a
            href="https://github.com/ishan1603/IronTest"
            target="_blank"
            rel="noreferrer"
            className="hidden rounded-pill px-4 py-2 text-sm text-muted transition-colors hover:text-ink sm:block"
          >
            Source
          </a>
          <a
            href={api.loginUrl()}
            className="inline-flex h-9 items-center rounded-pill border border-line/25 px-4 text-sm transition-colors hover:border-accent hover:text-accent"
          >
            Sign in
          </a>
        </nav>
      </div>
    </header>
  );
}

function GitHubMark() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
    </svg>
  );
}
