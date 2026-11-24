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
          50: '#e6f2f0',
          100: '#b3ddd7',
          200: '#80c8be',
          300: '#4db3a5',
          400: '#26a392',
          500: '#04534a',
          600: '#044d44',
          700: '#03403a',
          800: '#02332f',
          900: '#011a18',
        },
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      }
    },
  },
  plugins: [],
}
