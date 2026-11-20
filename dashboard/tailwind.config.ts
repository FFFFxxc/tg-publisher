import type { Config } from "tailwindcss";

const colors = Object.fromEntries([
  "paper", "tint", "selected", "line", "line-strong", "ink", "muted", "subtle", "accent", "accent-hover",
  "success", "success-tint", "success-line", "warning", "warning-tint", "warning-line",
  "danger", "danger-tint", "danger-line", "info", "info-tint", "info-line",
].map(name => [name, `var(--${name})`]));

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: { colors, boxShadow: { card: "var(--card-shadow)" } },
  },
  plugins: [],
};
export default config;
