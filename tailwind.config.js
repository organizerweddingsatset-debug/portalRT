/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    "./templates/**/*.html",
    "./static/**/*.js"
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#eef2ff',
          100: '#e0e7ff',
          500: '#6366f1',
          600: '#4f46e5',
          700: '#4338ca',
        },
        dark: {
          main: '#0a0e1c',
          sidebar: '#0d1224',
          card: '#13192f',
          cardHover: '#18203c',
          border: '#1f2a4a'
        }
      }
    }
  },
  plugins: [],
}
