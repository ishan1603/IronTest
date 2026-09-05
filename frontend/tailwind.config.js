/** @type {import('tailwindcss').Config} */

// Walbi-inspired system: a near-black ground that inverts to full white for
// emphasis sections, one neon accent used sparingly as signal, and oversized
// display type. Colours resolve through CSS variables so an inverted section
// flips the whole scale by setting one attribute.
export default {
  darkMode: ["class", '[data-theme="light"]'],
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        page: "rgb(var(--page) / <alpha-value>)",
        surface: "rgb(var(--surface) / <alpha-value>)",
        ink: "rgb(var(--ink) / <alpha-value>)",
        muted: "rgb(var(--muted) / <alpha-value>)",
        line: "rgb(var(--line) / <alpha-value>)",
        contrast: "rgb(var(--contrast) / <alpha-value>)",
        "contrast-ink": "rgb(var(--contrast-ink) / <alpha-value>)",
        // The single accent. Signal only: live state, pass, active step.
        accent: "rgb(var(--accent) / <alpha-value>)",
        "accent-dim": "rgb(var(--accent-dim) / <alpha-value>)",
        success: "rgb(var(--accent) / <alpha-value>)",
        warning: "#F5A524",
        danger: "#FF4D4D",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        display: ['"Space Grotesk"', "Inter", "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      fontSize: {
        xs: ["0.75rem", { lineHeight: "1.1rem" }],
        sm: ["0.875rem", { lineHeight: "1.375rem" }],
        base: ["1rem", { lineHeight: "1.6rem" }],
        lg: ["1.25rem", { lineHeight: "1.6rem" }],
        xl: ["1.75rem", { lineHeight: "1.15" }],
        "2xl": ["2.5rem", { lineHeight: "1.05" }],
        "3xl": ["4rem", { lineHeight: "0.95" }],
        // Oversized display sizes that bleed off the edges.
        mega: ["clamp(3.5rem, 12vw, 11rem)", { lineHeight: "0.86", letterSpacing: "-0.03em" }],
        giga: ["clamp(5rem, 22vw, 20rem)", { lineHeight: "0.8", letterSpacing: "-0.04em" }],
      },
      spacing: { 1: "4px", 2: "8px", 3: "12px", 4: "16px", 6: "24px", 8: "32px", 18: "72px" },
      borderRadius: { sm: "4px", DEFAULT: "8px", md: "10px", lg: "16px", pill: "999px" },
      maxWidth: { prose: "62ch", shell: "1440px" },
      keyframes: {
        "fade-up": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "tick-pulse": {
          "0%, 100%": { opacity: "0.25", transform: "scaleY(0.6)" },
          "50%": { opacity: "1", transform: "scaleY(1)" },
        },
        marquee: {
          from: { transform: "translateX(0)" },
          to: { transform: "translateX(-50%)" },
        },
      },
      animation: {
        "fade-up": "fade-up 320ms cubic-bezier(0.22,1,0.36,1) both",
        "tick-pulse": "tick-pulse 1.4s ease-in-out infinite",
        marquee: "marquee 28s linear infinite",
      },
    },
  },
  plugins: [],
};
