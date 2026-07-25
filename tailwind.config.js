/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'navy': {
          '900': '#0f172a',
          '800': '#1e293b',
          '700': '#334155',
          '600': '#475569',
        },
        'hype': {
          'yellow': '#fcd34d',
          'light': '#f8fafc',
          'white': '#ffffff',
          'gray': '#f1f5f9',
        }
      },
      spacing: {
        safe: "env(safe-area-inset-bottom)",
      }
    },
  },
  plugins: [],
}
