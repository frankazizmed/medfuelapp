import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: {
          50: '#f7f8fb',
          100: '#edf0f5',
          200: '#d9dee7',
          400: '#7b8499',
          600: '#3d4659',
          800: '#1f2433',
          900: '#101422',
        },
        signal: {
          50: '#eaf6ee',
          400: '#3b9b58',
          600: '#1c7a3a',
        },
        risk: {
          50: '#fbecea',
          400: '#c5483a',
          600: '#9a2f24',
        },
        rule: '#dde2eb',
      },
      fontFamily: {
        serif: ['"Source Serif Pro"', 'Georgia', 'serif'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
    },
  },
  plugins: [],
};

export default config;
