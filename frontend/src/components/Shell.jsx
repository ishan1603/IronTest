import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import clsx from "clsx";
import { useAuth } from "../lib/auth";
import { Button } from "./ui";

const THEME_KEY = "irontest.theme";

function useTheme() {
  const [theme, setTheme] = useState(() => {
    try {
      return localStorage.getItem(THEME_KEY) || "system";
    } catch {
      return "system";
    }
  });

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch {
      /* Theme simply will not persist. */
    }
  }, [theme]);

  return [theme, setTheme];
}

function ThemeToggle() {
  const [theme, setTheme] = useTheme();
  const next = { system: "light", light: "dark", dark: "system" }[theme];
  const glyph = { system: "Auto", light: "Light", dark: "Dark" }[theme];

  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={() => setTheme(next)}
      aria-label={`Theme: ${glyph}. Switch to ${next}.`}
      className="font-mono uppercase tracking-wider"
    >
      {glyph}
    </Button>
  );
}

export function Shell({ children, aside }) {
  const { user, signOut } = useAuth();
  const { pathname } = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);

  // Close the mobile drawer whenever the route changes.
  useEffect(() => setMenuOpen(false), [pathname]);

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-30 border-b border-line/15 bg-page/95 backdrop-blur">
        <div className="mx-auto flex h-14 w-full max-w-[1400px] items-center gap-4 px-4 sm:px-6">
          <Link to="/" className="font-mono text-sm font-bold uppercase tracking-[0.18em]">
            Irontest
          </Link>

          <nav className="hidden items-center gap-1 sm:flex" aria-label="Main">
            <NavLink to="/dashboard" active={pathname.startsWith("/dashboard")}>
              Repositories
            </NavLink>
            <NavLink to="/runs" active={pathname.startsWith("/runs")}>
              Runs
            </NavLink>
          </nav>

          <div className="ml-auto flex items-center gap-2">
            <ThemeToggle />
            {user && (
              <>
                <span className="hidden items-center gap-2 sm:flex">
                  {user.avatar_url && (
                    <img
                      src={user.avatar_url}
                      alt=""
                      width={24}
                      height={24}
                      className="rounded-pill border border-line/20"
                    />
                  )}
                  <span className="text-sm text-muted">{user.login}</span>
                </span>
                <Button variant="secondary" size="sm" onClick={signOut} className="hidden sm:inline-flex">
                  Sign out
                </Button>
              </>
            )}
            <button
              className="sm:hidden"
              onClick={() => setMenuOpen((open) => !open)}
              aria-expanded={menuOpen}
              aria-label="Menu"
            >
              <span className="block h-px w-5 bg-ink" />
              <span className="mt-1.5 block h-px w-5 bg-ink" />
              <span className="mt-1.5 block h-px w-5 bg-ink" />
            </button>
          </div>
        </div>

        {menuOpen && (
          <div className="border-t border-line/15 px-4 py-3 sm:hidden">
            <nav className="flex flex-col gap-1" aria-label="Mobile">
              <NavLink to="/dashboard" active={pathname.startsWith("/dashboard")}>
                Repositories
              </NavLink>
              <NavLink to="/runs" active={pathname.startsWith("/runs")}>
                Runs
              </NavLink>
              {user && (
                <button onClick={signOut} className="px-3 py-2 text-left text-sm text-muted">
                  Sign out ({user.login})
                </button>
              )}
            </nav>
          </div>
        )}
      </header>

      <div className="mx-auto flex w-full max-w-[1400px] flex-1 flex-col lg:flex-row">
        {aside && (
          <aside className="shrink-0 border-b border-line/15 lg:w-72 lg:border-b-0 lg:border-r">{aside}</aside>
        )}
        <main className="min-w-0 flex-1">{children}</main>
      </div>
    </div>
  );
}

function NavLink({ to, active, children }) {
  return (
    <Link
      to={to}
      aria-current={active ? "page" : undefined}
      className={clsx(
        "rounded-pill px-3 py-1.5 text-sm transition-colors",
        active ? "bg-contrast text-contrast-ink" : "text-muted hover:text-ink",
      )}
    >
      {children}
    </Link>
  );
}
