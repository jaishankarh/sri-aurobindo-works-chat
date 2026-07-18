/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // stone/amber are redefined here (rather than left as Tailwind's
        // static built-ins) to read from CSS custom properties instead —
        // every existing `bg-stone-200`, `text-amber-600`, etc. class
        // across the app becomes theme-aware automatically, driven by
        // whichever [data-theme] block is active (see index.css). No
        // component needed to change its class names for theming to work.
        stone: {
          50: "rgb(var(--color-stone-50) / <alpha-value>)",
          100: "rgb(var(--color-stone-100) / <alpha-value>)",
          200: "rgb(var(--color-stone-200) / <alpha-value>)",
          300: "rgb(var(--color-stone-300) / <alpha-value>)",
          400: "rgb(var(--color-stone-400) / <alpha-value>)",
          500: "rgb(var(--color-stone-500) / <alpha-value>)",
          600: "rgb(var(--color-stone-600) / <alpha-value>)",
          700: "rgb(var(--color-stone-700) / <alpha-value>)",
          800: "rgb(var(--color-stone-800) / <alpha-value>)",
          900: "rgb(var(--color-stone-900) / <alpha-value>)",
        },
        amber: {
          50: "rgb(var(--color-amber-50) / <alpha-value>)",
          100: "rgb(var(--color-amber-100) / <alpha-value>)",
          200: "rgb(var(--color-amber-200) / <alpha-value>)",
          300: "rgb(var(--color-amber-300) / <alpha-value>)",
          400: "rgb(var(--color-amber-400) / <alpha-value>)",
          500: "rgb(var(--color-amber-500) / <alpha-value>)",
          600: "rgb(var(--color-amber-600) / <alpha-value>)",
          700: "rgb(var(--color-amber-700) / <alpha-value>)",
          800: "rgb(var(--color-amber-800) / <alpha-value>)",
          900: "rgb(var(--color-amber-900) / <alpha-value>)",
        },
        // Panel/card background — was hardcoded `bg-white` everywhere;
        // replaced with this so surfaces actually go dark/sepia/etc. too.
        surface: "rgb(var(--color-surface) / <alpha-value>)",
      },
      fontFamily: {
        serif: ["Georgia", "Cambria", '"Times New Roman"', "Times", "serif"],
        sans: [
          "Inter",
          "system-ui",
          "-apple-system",
          "BlinkMacSystemFont",
          "sans-serif",
        ],
        mono: ['"JetBrains Mono"', '"Fira Code"', "Consolas", "monospace"],
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-in": "fadeIn 0.3s ease-in-out",
        "slide-up": "slideUp 0.3s ease-out",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%": { transform: "translateY(8px)", opacity: "0" },
          "100%": { transform: "translateY(0)", opacity: "1" },
        },
      },
    },
  },
  plugins: [],
};
