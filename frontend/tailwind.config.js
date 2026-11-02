/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: { ink: { 950: '#0b1220', 900: '#0d1626', 800: '#111d30', 700: '#223047', 600: '#2c3c53' }, accent: '#3ccfb8' },
      fontFamily: { mono: ['"DM Mono"', 'ui-monospace', 'monospace'] },
    },
  },
  plugins: [],
};
