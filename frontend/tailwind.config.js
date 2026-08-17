/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./features/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#07090d",
          900: "#0b1016",
          800: "#101820",
          700: "#16202b",
          600: "#1d2a38",
        },
        line: "#243140",
        gold: "#c8a15a",
        gain: "#3dd68c",
        loss: "#ef6b6b",
        warn: "#e7b549",
        mist: "#9bb0c3",
      },
      fontFamily: {
        sans: ["IBM Plex Sans", "ui-sans-serif", "system-ui"],
        mono: ["IBM Plex Mono", "ui-monospace", "SFMono-Regular"],
      },
      boxShadow: {
        terminal: "0 12px 40px rgba(0,0,0,0.35)",
      },
    },
  },
  plugins: [],
};
