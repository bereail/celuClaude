/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        base: "#0b0d12",
        panel: "#11141b",
        accent: "#7c5cff",
        online: "#22c55e",
        offline: "#ef4444",
        warn: "#f59e0b",
      },
    },
  },
  plugins: [],
};
