/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // RevenueForge brand
        brand: { 50: "#EAF5FB", 100: "#CFE8F5", 200: "#9FD1EB", 400: "#3BA3D6", 500: "#118AC3", 600: "#067AB0", 700: "#0B638E", 800: "#125C7E", 900: "#0C3D55", 950: "#082B3D" },
        ember: { 50: "#FEF3EB", 100: "#FDE2CF", 400: "#F79A5E", 500: "#F5833A", 600: "#DD6A22" },
        ink: { DEFAULT: "#10222E", soft: "#3D4F5B", muted: "#5F707B", faint: "#8A99A3" },
        paper: "#F3F6F8",
        line: { DEFAULT: "#DCE3E8", soft: "#E8EDF0" },
        // match status: validated for colour-blind separation (strong blue-teal, partial amber, gap red; confirm drawn hollow)
        fit: { strong: "#1A82AE", partial: "#D09516", gap: "#CC3D3D", confirm: "#8A99A3",
               "strong-ink": "#13698D", "partial-ink": "#8A5F07", "gap-ink": "#A8302F", "confirm-ink": "#56656F" },
        // "good" status (approved, won, saved), never used for match strength
        ok: { DEFAULT: "#17876A", bg: "#E3F4EE" },
      },
      fontFamily: {
        sans: ["'Hanken Grotesk Variable'", "'Hanken Grotesk'", "system-ui", "sans-serif"],
        doc: ["'Newsreader Variable'", "'Newsreader'", "Georgia", "serif"],
        display: ["'Newsreader Variable'", "'Newsreader'", "Georgia", "serif"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(16,34,46,.06), 0 1px 1px rgba(16,34,46,.04)",
        lift: "0 12px 32px -12px rgba(12,61,85,.28)",
      },
    },
  },
  plugins: [],
};
