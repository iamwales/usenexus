import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}"
  ],
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: {
        "2xl": "1200px"
      }
    },
    extend: {
      colors: {
        border: "var(--border)",
        input: "var(--border-2)",
        ring: "var(--text)",
        background: "var(--bg)",
        foreground: "var(--text)",
        primary: {
          DEFAULT: "var(--primary)",
          foreground: "var(--accent-fg)"
        },
        secondary: {
          DEFAULT: "var(--bg-alt)",
          foreground: "var(--text)"
        },
        muted: {
          DEFAULT: "var(--bg-alt)",
          foreground: "var(--text-2)"
        },
        accent: {
          DEFAULT: "var(--accent)",
          foreground: "var(--accent-fg)"
        },
        card: {
          DEFAULT: "var(--surface)",
          foreground: "var(--text)"
        }
      },
      borderRadius: {
        lg: "var(--radius-lg)",
        md: "var(--radius-md)",
        sm: "var(--radius)"
      },
      fontFamily: {
        sans: ["var(--sans)"],
        mono: ["var(--mono)"]
      },
      boxShadow: {
        soft: "var(--shadow)",
        panel: "var(--shadow-md)",
        lift: "var(--shadow-xl)"
      }
    }
  },
  plugins: [require("tailwindcss-animate")]
};

export default config;
