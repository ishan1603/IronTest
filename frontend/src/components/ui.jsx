import clsx from "clsx";
import { useMemo } from "react";
import { motion, useReducedMotion } from "framer-motion";

// Codex primitives. Every interactive element is a pill; every boundary is a
// hairline; nothing casts a shadow or carries a gradient.

const BUTTON_VARIANTS = {
  primary: "bg-contrast text-contrast-ink hover:opacity-85 disabled:opacity-40",
  secondary: "bg-transparent text-ink border border-line/25 hover:border-line/60 disabled:opacity-40",
  ghost: "bg-transparent text-muted hover:text-ink disabled:opacity-40",
  danger: "bg-transparent text-danger border border-danger/30 hover:border-danger disabled:opacity-40",
};

const BUTTON_SIZES = {
  sm: "h-8 px-3 text-xs",
  md: "h-10 px-4 text-sm",
  lg: "h-12 px-6 text-sm",
};

export function Button({ variant = "primary", size = "md", className, as: Tag = "button", ...props }) {
  const reduce = useReducedMotion();
  // Memoised: motion(Tag) creates a component; doing it inline would remount children each render.
  const MotionTag = useMemo(() => motion(Tag), [Tag]);
  return (
    <MotionTag
      whileHover={reduce || props.disabled ? undefined : { y: -1 }}
      whileTap={reduce || props.disabled ? undefined : { scale: 0.97 }}
      transition={{ type: "spring", stiffness: 500, damping: 30 }}
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-pill font-medium",
        "transition-colors duration-150 disabled:cursor-not-allowed",
        BUTTON_VARIANTS[variant],
        BUTTON_SIZES[size],
        className,
      )}
      {...props}
    />
  );
}

/** Shimmering placeholder block for loading states. */
export function Skeleton({ className }) {
  return (
    <div
      className={clsx(
        "animate-pulse rounded-md bg-line/10",
        className,
      )}
    />
  );
}

/** Fade + rise wrapper for page content and list items. */
export function Reveal({ children, delay = 0, className }) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32, delay, ease: [0.22, 1, 0.36, 1] }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

export function Label({ children, className }) {
  return <span className={clsx("label-caps", className)}>{children}</span>;
}

export function Card({ className, contrast = false, ...props }) {
  return <div className={clsx(contrast ? "card-contrast" : "card", className)} {...props} />;
}

/** Small pill used for stack tags, languages, counts. */
export function Tag({ children, className, tone = "default" }) {
  const tones = {
    default: "border-line/20 text-muted",
    solid: "border-transparent bg-contrast text-contrast-ink",
    success: "border-success/30 text-success",
    danger: "border-danger/30 text-danger",
    warning: "border-warning/30 text-warning",
  };
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded-pill border px-2 py-0.5 font-mono text-xs",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

/** Status dot + text for a single test outcome. */
export function StatusDot({ status }) {
  const map = {
    pass: ["bg-success", "Passed"],
    fail: ["bg-danger", "Failed"],
    error: ["bg-danger", "Error"],
    skipped: ["bg-muted", "Skipped"],
  };
  const [dot, text] = map[status] || map.skipped;
  return (
    <span className="inline-flex items-center gap-2">
      <span className={clsx("h-2 w-2 shrink-0 rounded-pill", dot)} aria-hidden="true" />
      <span className="text-sm">{text}</span>
    </span>
  );
}

export function Spinner({ className }) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={clsx(
        "inline-block h-4 w-4 animate-spin rounded-pill border-2 border-line/20 border-t-ink",
        className,
      )}
    />
  );
}

export function EmptyState({ title, description, action }) {
  return (
    <div className="flex flex-col items-center gap-3 px-6 py-16 text-center">
      <p className="text-lg font-semibold">{title}</p>
      {description && <p className="max-w-prose text-sm text-muted">{description}</p>}
      {action}
    </div>
  );
}

export function Banner({ tone = "danger", children, onDismiss }) {
  const tones = {
    danger: "border-danger/30 text-danger",
    warning: "border-warning/30 text-warning",
    info: "border-line/20 text-muted",
  };
  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      className={clsx("flex items-start gap-3 rounded-md border px-4 py-3 text-sm", tones[tone])}
    >
      <span className="flex-1">{children}</span>
      {onDismiss && (
        <button onClick={onDismiss} className="shrink-0 text-xs underline" aria-label="Dismiss">
          Dismiss
        </button>
      )}
    </div>
  );
}

/** Horizontal meter. Used for pass rate and confidence, never for decoration. */
export function Meter({ value, max = 100, tone = "contrast", label }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  const fills = {
    contrast: "bg-contrast",
    success: "bg-success",
    warning: "bg-warning",
    danger: "bg-danger",
  };
  return (
    <div
      role="meter"
      aria-valuenow={Math.round(value)}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-label={label}
      className="h-1.5 w-full overflow-hidden rounded-pill bg-line/10"
    >
      <div className={clsx("h-full rounded-pill transition-[width] duration-500", fills[tone])} style={{ width: `${pct}%` }} />
    </div>
  );
}
