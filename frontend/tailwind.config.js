/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{html,js,svelte,ts}'],
  theme: {
    extend: {
      colors: {
        bg: 'var(--bg)',
        bg2: 'var(--bg2)',
        'bg-soft': 'var(--bg-soft)',
        ink: 'var(--ink)',
        muted: 'var(--muted)',
        rule: 'var(--rule)',
        accent: {
          DEFAULT: 'var(--accent)',
          soft: 'var(--accent-soft)'
        },
        accent2: {
          DEFAULT: 'var(--accent2)',
          soft: 'var(--accent2-soft)'
        },
        ok: {
          DEFAULT: 'var(--ok)',
          soft: 'var(--ok-soft)'
        },
        neutral: 'var(--neutral)'
      },
      borderRadius: {
        DEFAULT: 'var(--radius)',
        card: 'var(--radius-card)',
        full: 'var(--radius-full)'
      },
      fontFamily: {
        sans: [
          '-apple-system',
          'BlinkMacSystemFont',
          'Segoe UI',
          'PingFang SC',
          'Microsoft YaHei',
          'sans-serif'
        ]
      }
    }
  },
  plugins: []
};
