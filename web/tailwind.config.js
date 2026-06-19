/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#FAFAFA",
        surface: "#FFFFFF",
        surface2: "#F4F4F5",
        border: "#E4E4E7",
        text: "#18181B",
        muted: "#71717A",
        primary: "#2563EB",
        success: "#16A34A",
        warning: "#D97706",
        danger: "#DC2626",
        info: "#0891B2",
      },
    },
  },
  plugins: [],
};
