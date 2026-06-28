/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        canvas: '#FFFFFF',
        paper: '#F6F7F5',
        ink: {
          DEFAULT: '#12151A',
          soft: '#5C6470',
          faint: '#9AA1AB',
        },
        line: '#E4E7EA',
        signal: {
          DEFAULT: '#2E5BFF',
          dark: '#1E3FCC',
          soft: '#EBF0FF',
        },
        calibrate: {
          DEFAULT: '#14B873',
          soft: '#E6F8EF',
        },
        flag: {
          DEFAULT: '#F2A93B',
          soft: '#FDF2E0',
        },
        redline: {
          DEFAULT: '#E5484D',
          soft: '#FCE8E8',
        },
        navy: '#0B1220',
      },
      fontFamily: {
        display: ['"Space Grotesk"', 'sans-serif'],
        body: ['Inter', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'monospace'],
      },
      backgroundImage: {
        grid: 'linear-gradient(rgba(18,21,26,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(18,21,26,0.05) 1px, transparent 1px)',
      },
      backgroundSize: {
        grid: '32px 32px',
      },
      boxShadow: {
        card: '0 1px 2px rgba(18,21,26,0.04), 0 8px 24px -8px rgba(18,21,26,0.08)',
        lift: '0 4px 6px rgba(18,21,26,0.04), 0 16px 32px -12px rgba(18,21,26,0.14)',
      },
    },
  },
  plugins: [],
};
