/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: "class",   // ✅ ADD THIS
  content: [
    "./src/**/*.{js,jsx,ts,tsx}"
  ],
  theme: {
    extend: {
      colors: {
        // Blue palette
        blue: {
          primary: "#3B82F6",
          secondary: "#2563EB",
          tertiary: "#1D4ED8",
          light: "#60A5FA",
          lighter: "#93C5FD",
          dark: "#1E40AF",
        },
        // Light Blue palette
        lightblue: {
          primary: "#0EA5E9",
          secondary: "#0284C7",
          light: "#38BDF8",
          lighter: "#7DD3FC",
          dark: "#0369A1",
        },
        // Dark backgrounds
        dark: {
          bg: "#0A0A0A",
          surface: "#111111",
          card: "#1A1A1A",
          border: "#2A2A2A",
          hover: "#252525",
        },
        // Light backgrounds
        light: {
          bg: "#FFFFFF",
          surface: "#FAFAFA",
          card: "#F5F5F5",
          border: "#E5E7EB",
          hover: "#F3F4F6",
        },
      },
      backgroundImage: {
        'gradient-blue-lightblue': 'linear-gradient(135deg, #3B82F6 0%, #0EA5E9 100%)',
        'gradient-blue': 'radial-gradient(circle, rgba(59, 130, 246, 0.3) 0%, transparent 70%)',
        'gradient-lightblue': 'radial-gradient(circle, rgba(14, 165, 233, 0.3) 0%, transparent 70%)',
        'gradient-blue-lightblue-light': 'linear-gradient(135deg, rgba(96, 165, 250, 0.15) 0%, rgba(56, 189, 248, 0.15) 100%)',
        'gradient-blue-light': 'radial-gradient(circle, rgba(96, 165, 250, 0.1) 0%, transparent 70%)',
        'gradient-lightblue-light': 'radial-gradient(circle, rgba(56, 189, 248, 0.1) 0%, transparent 70%)',
      },
      boxShadow: {
        'glow-blue': '0 0 20px rgba(59, 130, 246, 0.5), 0 0 40px rgba(59, 130, 246, 0.3)',
        'glow-lightblue': '0 0 20px rgba(14, 165, 233, 0.5), 0 0 40px rgba(14, 165, 233, 0.3)',
        'glow-orb': '0 0 60px rgba(59, 130, 246, 0.6), 0 0 100px rgba(37, 99, 235, 0.4), 0 0 140px rgba(14, 165, 233, 0.2)',
      },
      backdropBlur: {
        xs: '2px',
      },
      animation: {
        'pulse-slow': 'pulse 4s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'glow': 'glow 3s ease-in-out infinite alternate',
      },
      keyframes: {
        glow: {
          '0%': { 
            boxShadow: '0 0 20px rgba(59, 130, 246, 0.5), 0 0 40px rgba(59, 130, 246, 0.3)',
          },
          '100%': { 
            boxShadow: '0 0 40px rgba(59, 130, 246, 0.8), 0 0 80px rgba(37, 99, 235, 0.6), 0 0 120px rgba(14, 165, 233, 0.4)',
          },
        },
      },
    },
  },
  plugins: [],
}
