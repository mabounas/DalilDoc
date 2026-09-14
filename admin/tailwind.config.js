/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        night: "#0D0D20",
        gold: "#C9A84C",
        mint: "#2A9D8F",
      },
    },
  },
  plugins: [],
};
