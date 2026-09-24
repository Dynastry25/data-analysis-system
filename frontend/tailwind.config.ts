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
          50: "#EFF6FF",
          100: "#DBEAFE",
          300: "#93C5FD",
          500: "#3B82F6",
          600: "#2563EB",
          700: "#1D4ED8",
          900: "#1E3A8A",
        },
        neutral: {
          50: "#F9FAFB",
          100: "#F3F4F6",
          200: "#E5E7EB",
          400: "#9CA3AF",
          600: "#4B5563",
          900: "#111827",
        },
        success: {
          DEFAULT: "#16A34A",
          bg: "#F0FDF4",
        },
        warning: {
          DEFAULT: "#D97706",
          bg: "#FFFBEB",
        },
        danger: {
          DEFAULT: "#DC2626",
          bg: "#FEF2F2",
        },
        info: {
          DEFAULT: "#0284C7",
          bg: "#F0F9FF",
        },
        // Okabe-Ito colorblind-safe chart palette (design system §2).
        // Keep in sync with lib/constants.ts CHART_PALETTE.
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
        display: ["32px", { lineHeight: "1.25", fontWeight: "600" }],
        h1: ["28px", { lineHeight: "1.25", fontWeight: "600" }],
        h2: ["22px", { lineHeight: "1.25", fontWeight: "500" }],
        h3: ["18px", { lineHeight: "1.25", fontWeight: "500" }],
        "body-lg": ["16px", { lineHeight: "1.5", fontWeight: "400" }],
        body: ["14px", { lineHeight: "1.5", fontWeight: "400" }],
        caption: ["12px", { lineHeight: "1.5", fontWeight: "400" }],
      },
      spacing: {
        "1.5x": "12px",
      },
      borderRadius: {
        DEFAULT: "8px",
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
