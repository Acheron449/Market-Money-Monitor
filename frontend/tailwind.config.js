/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "hsl(160 27% 6%)",
        card: "hsl(157 25% 10%)",
        fg: "hsl(150 16% 91%)",
        line: "hsl(150 24% 16%)",
        muted: "hsl(153 9% 54%)",
        champagne: "hsl(45 51% 70%)",
        buy: "hsl(145 63% 49%)",
        sell: "hsl(6 53% 49%)",
      },
      fontFamily: {
        display: ['"Cormorant Garamond"', "Georgia", "serif"],
        sans: ["Inter", "system-ui", "-apple-system", "sans-serif"],
      },
      boxShadow: {
        tile: "0 1px 0 0 hsl(150 24% 16%), 0 12px 24px -18px rgb(0 0 0 / 0.9)",
      },
    },
  },
  plugins: [],
};
