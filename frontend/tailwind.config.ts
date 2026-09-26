import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50: "#EEF2FF",
          100: "#E0E7FF",
          200: "#C7D2FE",
          300: "#A5B4FC",
          400: "#818CF8",
          500: "#6366F1",
          600: "#4F46E5",
          700: "#4338CA",
          800: "#3730A3",
          900: "#312E81",
        },
        accent: {
          50: "#ECFEFF",
          100: "#CFFAFE",
          200: "#A5F3FC",
          300: "#67E8F9",
          400: "#22D3EE",
          500: "#06B6D4",
          600: "#0891B2",
          700: "#0E7490",
          900: "#164E63",
        },
        neutral: {
          50: "#F8FAFC",
          100: "#F1F5F9",
          200: "#E2E8F0",
          300: "#CBD5E1",
          400: "#94A3B8",
          500: "#64748B",
          600: "#475569",
          700: "#334155",
          800: "#1E293B",
          900: "#0F172A",
        },
        surface: {
          canvas: "#F8FAFC",
          panel: "#FFFFFF",
          sunken: "#F1F5F9",
          raised: "#FFFFFF",
          border: "#E2E8F0",
          "border-strong": "#CBD5E1",
        },
        ink: {
          DEFAULT: "#0F172A",
          secondary: "#475569",
          muted: "#64748B",
          inverse: "#F8FAFC",
        },
        success: {
          DEFAULT: "#16A34A",
          700: "#15803D",
          bg: "#F0FDF4",
        },
        warning: {
          DEFAULT: "#D97706",
          700: "#B45309",
          bg: "#FFFBEB",
        },
        danger: {
          DEFAULT: "#DC2626",
          700: "#B91C1C",
          bg: "#FEF2F2",
        },
        info: {
          DEFAULT: "#0284C7",
          700: "#0369A1",
          bg: "#F0F9FF",
        },
        chart: {
          1: "#0072B2",
          2: "#E69F00",
          3: "#009E73",
          4: "#CC79A7",
          5: "#56B4E9",
          6: "#D55E00",
          7: "#F0E442",
          8: "#999999",
        },
      },
      fontFamily: {
        sans: ["var(--font-inter)", "-apple-system", "Segoe UI", "sans-serif"],
        mono: ["var(--font-ibm-plex-mono)", "Roboto Mono", "monospace"],
      },
      fontSize: {
        display: ["32px", { lineHeight: "1.25", fontWeight: "600", letterSpacing: "-0.02em" }],
        h1: ["28px", { lineHeight: "1.25", fontWeight: "600", letterSpacing: "-0.015em" }],
        h2: ["22px", { lineHeight: "1.3", fontWeight: "600", letterSpacing: "-0.01em" }],
        h3: ["18px", { lineHeight: "1.35", fontWeight: "600" }],
        "body-lg": ["16px", { lineHeight: "1.5", fontWeight: "400" }],
        body: ["14px", { lineHeight: "1.5", fontWeight: "400" }],
        caption: ["12px", { lineHeight: "1.5", fontWeight: "400" }],
        overline: [
          "11px",
          { lineHeight: "1.4", fontWeight: "600", letterSpacing: "0.08em" },
        ],
      },
      spacing: {
        "1.5x": "12px",
        gutter: "24px",
        "page-x": "32px",
      },
      borderRadius: {
        DEFAULT: "8px",
        sm: "6px",
        md: "8px",
        lg: "12px",
        pill: "999px",
      },
      boxShadow: {
        card: "0 1px 2px 0 rgb(15 23 42 / 0.04)",
        raised: "0 4px 12px -2px rgb(15 23 42 / 0.08)",
        drawer: "0 8px 32px -8px rgb(15 23 42 / 0.24)",
        overlay: "0 16px 48px -12px rgb(15 23 42 / 0.28)",
        "focus-ring": "0 0 0 3px rgb(79 70 229 / 0.28)",
      },
      maxWidth: {
        content: "1440px",
      },
      transitionTimingFunction: {
        standard: "cubic-bezier(0.2, 0, 0, 1)",
      },
      ringColor: {
        DEFAULT: "rgb(79 70 229 / 0.45)",
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "scale-in": {
          from: { opacity: "0", transform: "scale(0.98)" },
          to: { opacity: "1", transform: "scale(1)" },
        },
        "slide-in-left": {
          from: { transform: "translateX(-100%)" },
          to: { transform: "translateX(0)" },
        },
      },
      animation: {
        "fade-in": "fade-in 200ms cubic-bezier(0.2, 0, 0, 1)",
        "scale-in": "scale-in 160ms cubic-bezier(0.2, 0, 0, 1)",
        "slide-in-left": "slide-in-left 260ms cubic-bezier(0.2, 0, 0, 1)",
      },
      screens: {
        sm: "640px",
        lg: "1024px",
      },
    },
  },
  plugins: [],
};

export default config;
