/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'IBM Plex Sans', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Menlo', 'monospace']
      },
      colors: {
        ink: {
          50: '#f6f7f8',
          100: '#e8eaed',
          200: '#d1d5db',
          300: '#b0b7c3',
          400: '#8a94a6',
          500: '#6b7280',
          600: '#4b5563',
          700: '#374151',
          800: '#1f2937',
          900: '#111827',
        },
        accent: {
          500: '#0e7490',
          600: '#0c6580',
        }
      }
    },
  },
  plugins: [],
}
