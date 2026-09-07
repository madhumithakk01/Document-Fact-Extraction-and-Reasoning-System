/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#191817",
        recessed: "#141312",
        raised: "#211F1D",
        hairline: "#2A2825",
        "text-primary": "#E9E5DE",
        "text-muted": "#948F88",
        accent: "#C96442",
        "accent-dim": "#7A4530",
        // semantic relationship / status (desaturated)
        corroborates: "#7FA285",
        contradicts: "#B85C4E",
        reconciled: "#C9A24B",
        review: "#8C8577",
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "sans-serif",
        ],
        mono: [
          "'JetBrains Mono'",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Consolas",
          "monospace",
        ],
      },
      fontSize: {
        title: ["20px", { lineHeight: "1.3", fontWeight: "600" }],
        section: ["14px", { lineHeight: "1.4", fontWeight: "600" }],
        body: ["15px", { lineHeight: "1.6" }],
        cell: ["13px", { lineHeight: "1.4" }],
        meta: ["12px", { lineHeight: "1.4" }],
      },
      spacing: {
        sidebar: "260px",
        evidence: "420px",
      },
      keyframes: {
        "pulse-once": {
          "0%": { backgroundColor: "rgba(201,100,66,0.42)" },
          "100%": { backgroundColor: "rgba(201,100,66,0.16)" },
        },
        "slide-in": {
          "0%": { transform: "translateX(24px)", opacity: "0" },
          "100%": { transform: "translateX(0)", opacity: "1" },
        },
      },
      animation: {
        "pulse-once": "pulse-once 900ms ease-out 1",
        "slide-in": "slide-in 180ms ease-out 1",
      },
    },
  },
  plugins: [],
};
