/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Hades palette — dark, underworld-inspired.
        hades: {
          bg: "#0b0b0f",
          panel: "#14141b",
          accent: "#e4572e",
          muted: "#6b7280",
        },
      },
    },
  },
  plugins: [],
};
