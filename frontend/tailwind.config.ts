import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      /*
       * Palette from the StatFlow design system (the Figma Make prototype in
       * `statflowUI/src/index.css`). Violet accent on warm greys, replacing the
       * indigo-on-slate it used to be.
       */
      colors: {
        primary: {
          50: "#F5F2FF",
          100: "#EFEBFF",
          200: "#DED5FF",
          300: "#C6B5FD",
          400: "#A78BFA",
          500: "#8B6BF7",
          600: "#6C4BF4",
          700: "#5A38D6",
          800: "#482CAC",
          900: "#33206F",
        },
        accent: {
          50: "#EAF2FF",
          100: "#EAF2FF",
          200: "#CFE0FF",
          300: "#A8C6FF",
          400: "#6FA1FB",
          500: "#3378F6",
          600: "#2563D9",
          700: "#1D4FB0",
          900: "#12336F",
        },
        neutral: {
          50: "#FAFAFC",
          100: "#F5F5F8",
          200: "#EFEDF2",
          300: "#E7E5EB",
          400: "#D4D1DA",
          500: "#A6A3AD",
          600: "#8C8896",
          700: "#777482",
          800: "#4A4753",
          900: "#2B2933",
        },
        surface: {
          canvas: "#F5F6FA",
          panel: "#FFFFFF",
          sunken: "#F8F8FB",
          raised: "#FFFFFF",
          border: "#E7E5EB",
          "border-strong": "#D4D1DA",
        },
        sidebar: {
          DEFAULT: "#111019",
          deep: "#0B0A11",
          active: "#292434",
        },
        ink: {
          DEFAULT: "#17151F",
          secondary: "#4A4753",
          muted: "#777482",
          inverse: "#F5F6FA",
        },
        success: {
          DEFAULT: "#24A36A",
          700: "#1B8556",
          bg: "#E7F7EF",
        },
        warning: {
          DEFAULT: "#E99B2D",
          700: "#B87A1C",
          bg: "#FFF4DF",
        },
        danger: {
          DEFAULT: "#DF5B5B",
          700: "#BC4343",
          bg: "#FDECEC",
        },
        info: {
          DEFAULT: "#3378F6",
          700: "#2563D9",
          bg: "#EAF2FF",
        },
        /*
         * Okabe-Ito, kept colour-blind safe. The brand violet is deliberately
         * not in this ramp: a categorical series that starts with the accent
         * makes "first series" indistinguishable from "brand".
         */
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
        sans: ["var(--font-dm-sans)", "system-ui", "Segoe UI", "sans-serif"],
        display: ["var(--font-manrope)", "var(--font-dm-sans)", "sans-serif"],
        mono: ["var(--font-ibm-plex-mono)", "Roboto Mono", "monospace"],
      },
      fontSize: {
        display: ["30px", { lineHeight: "1.2", fontWeight: "700", letterSpacing: "-0.02em" }],
        h1: ["24px", { lineHeight: "1.2", fontWeight: "700", letterSpacing: "-0.015em" }],
        h2: ["19px", { lineHeight: "1.25", fontWeight: "700", letterSpacing: "-0.01em" }],
        h3: ["16px", { lineHeight: "1.3", fontWeight: "700" }],
        "body-lg": ["15px", { lineHeight: "1.5", fontWeight: "400" }],
        body: ["14px", { lineHeight: "1.5", fontWeight: "400" }],
        caption: ["12.5px", { lineHeight: "1.45", fontWeight: "400" }],
        overline: [
          "10.5px",
          { lineHeight: "1.4", fontWeight: "600", letterSpacing: "0.09em" },
        ],
      },
      spacing: {
        "1.5x": "12px",
        gutter: "24px",
        "page-x": "32px",
      },
      borderRadius: {
        DEFAULT: "13px",
        sm: "8px",
        md: "11px",
        lg: "16px",
        pill: "999px",
      },
      boxShadow: {
        card: "0 1px 2px 0 rgb(24 20 34 / 0.02)",
        raised: "0 10px 28px -8px rgb(31 26 44 / 0.09)",
        hover: "0 10px 28px -10px rgb(31 26 44 / 0.12)",
        drawer: "0 8px 32px -8px rgb(24 20 34 / 0.2)",
        overlay: "0 24px 80px -12px rgb(14 10 22 / 0.28)",
        "focus-ring": "0 0 0 3px rgb(108 75 244 / 0.24)",
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
