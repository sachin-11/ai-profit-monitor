import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{js,ts,jsx,tsx,mdx}", "./components/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        ink: "#102a2b",
        mint: "#54d6b7",
        canvas: "#f4f8f6",
      },
      boxShadow: {
        card: "0 24px 80px -36px rgba(16, 42, 43, 0.35)",
      },
    },
  },
  plugins: [],
};

export default config;

