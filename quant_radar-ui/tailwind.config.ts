import type { Config } from "tailwindcss";

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Match Streamlit's default dark theme tones so the cutover is
        // visually consistent.
        bg: "#0e1117",
        panel: "#1c1f26",
        border: "#262730",
        text: "#fafafa",
        muted: "#9ca3af",
        accent: "#ff4b4b",
      },
    },
  },
  plugins: [],
} satisfies Config;
