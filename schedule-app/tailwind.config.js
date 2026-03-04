/** @type {import('tailwindcss').Config} */
export default {
  important: '#schedule-app',
  content: ['./src/**/*.{ts,tsx}'],
  corePlugins: {
    preflight: false,
  },
  theme: {
    extend: {
      colors: {
        'site-accent': '#5e1985',
        'site-bg': '#ffffff',
        'site-fg': '#1a1a2e',
        'site-muted': '#777',
        'site-border': '#e0e0e0',
        'cat-education': '#3B82F6',
        'cat-seminar': '#10B981',
        'cat-debate': '#F59E0B',
        'cat-hearing': '#EF4444',
        'cat-conference': '#8B5CF6',
        'cat-art': '#EC4899',
        'cat-event': '#F97316',
      },
      fontFamily: {
        sans: ["'Noto Sans KR'", '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
