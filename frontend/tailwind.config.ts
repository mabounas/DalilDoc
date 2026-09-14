import type { Config } from "tailwindcss";

// Design system CDC §07 : nuit profonde, or, vert menthe ; texte ≥ 18px, cibles ≥ 60px.
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        night: { DEFAULT: "#0D0D20", 800: "#15152E", 700: "#1E1E3F", 600: "#2A2A52" },
        gold: { DEFAULT: "#C9A84C", light: "#E3C878" },
        mint: { DEFAULT: "#2A9D8F", light: "#3FBFAF" },
        ink: { DEFAULT: "#F4F1E8", muted: "#B9B6C8" },
      },
      fontFamily: { sans: ["var(--font-plex-arabic)", "system-ui", "sans-serif"] },
      fontSize: { base: ["18px", "1.6"], lg: ["22px", "1.5"], xl: ["24px", "1.45"], "2xl": ["30px", "1.3"], "3xl": ["40px", "1.2"] },
      minHeight: { touch: "60px" },
      minWidth: { touch: "60px" },
      keyframes: {
        pulseRing: { "0%": { transform: "scale(1)", opacity: "0.6" }, "100%": { transform: "scale(1.6)", opacity: "0" } },
        floatY: { "0%,100%": { transform: "translateY(0)" }, "50%": { transform: "translateY(-12px)" } },
      },
      animation: { pulseRing: "pulseRing 1.6s ease-out infinite", floatY: "floatY 4s ease-in-out infinite" },
    },
  },
  plugins: [],
};

export default config;
