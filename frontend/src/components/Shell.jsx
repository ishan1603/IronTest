import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import clsx from "clsx";
import { useAuth } from "../lib/auth";
import { Button } from "./ui";
import { Tick } from "./motifs";

const NAV = [
  ["/dashboard", "Repositories"],
  ["/runs", "Analytics"],
  ["/integrations", "Integrations"],
];

export function Shell({ children, aside }) {
  const { user, signOut } = useAuth();
  const { pathname } = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);

  // Close the mobile drawer whenever the route changes.
  useEffect(() => setMenuOpen(false), [pathname]);

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-30 border-b border-line/10 bg-page/80 backdrop-blur-md">
        <div className="mx-auto flex h-14 w-full max-w-shell items-center gap-4 px-4 sm:px-6">
          <Link to="/dashboard" className="flex items-center gap-2">
            <Tick height={14} />
            <span className="font-display text-sm font-bold uppercase tracking-[0.14em]">
              Irontest
            </span>
          </Link>

          <nav className="hidden items-center gap-1 sm:flex" aria-label="Main">
            {NAV.map(([to, label]) => (
              <NavLink key={to} to={to} active={isActive(pathname, to)}>
                {label}
              </NavLink>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-2">
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
                  <span className="font-mono text-xs text-muted">{user.login}</span>
                </span>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={signOut}
                  className="hidden sm:inline-flex"
                >
                  Sign out
                </Button>
              </>
            )}
            <button
              className="flex h-9 w-9 flex-col items-center justify-center gap-1.5 sm:hidden"
              onClick={() => setMenuOpen((open) => !open)}
              aria-expanded={menuOpen}
              aria-label="Menu"
            >
              <span
                className={clsx(
                  "block h-px w-5 bg-ink transition-transform duration-200",
                  menuOpen && "translate-y-[6px] rotate-45",
                )}
              />
              <span
                className={clsx(
                  "block h-px w-5 bg-ink transition-opacity duration-200",
                  menuOpen && "opacity-0",
                )}
              />
              <span
                className={clsx(
                  "block h-px w-5 bg-ink transition-transform duration-200",
                  menuOpen && "-translate-y-[6px] -rotate-45",
                )}
              />
            </button>
          </div>
        </div>

        {menuOpen && (
          <div className="border-t border-line/10 px-4 py-3 sm:hidden">
            <nav className="flex flex-col gap-1" aria-label="Mobile">
              {NAV.map(([to, label]) => (
                <NavLink key={to} to={to} active={isActive(pathname, to)}>
                  {label}
                </NavLink>
              ))}
              {user && (
                <button
                  onClick={signOut}
                  className="px-3 py-2 text-left text-sm text-muted hover:text-ink"
                >
                  Sign out ({user.login})
                </button>
              )}
            </nav>
          </div>
        )}
      </header>

      <div className="mx-auto flex w-full max-w-shell flex-1 flex-col lg:flex-row">
        {aside && (
          <aside className="shrink-0 border-b border-line/10 lg:w-72 lg:border-b-0 lg:border-r">
            {aside}
          </aside>
        )}
        <main className="min-w-0 flex-1">{children}</main>
      </div>
    </div>
  );
}

/** /runs must not light up when the route is /runs/:id handled by another tab. */
function isActive(pathname, to) {
  return pathname === to || pathname.startsWith(`${to}/`);
}

function NavLink({ to, active, children }) {
  return (
    <Link
      to={to}
      aria-current={active ? "page" : undefined}
      className={clsx(
        "relative rounded-pill px-3 py-1.5 text-sm transition-colors",
        active ? "text-ink" : "text-muted hover:text-ink",
      )}
    >
      {children}
      {active && (
        <span
          aria-hidden="true"
          className="absolute inset-x-3 -bottom-0.5 h-px bg-accent"
          style={{ boxShadow: "0 0 8px rgb(var(--accent)/0.8)" }}
        />
      )}
    </Link>
  );
}
