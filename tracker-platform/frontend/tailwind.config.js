/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{html,ts}"],
  // evita choques de clases con los componentes de PrimeNG (que usan "p-" y
  // similares) -- preflight de Tailwind resetea estilos base que PrimeNG
  // tambien asume, asi que se desactiva y se deja que PrimeNG ponga su base
  corePlugins: { preflight: false },
  theme: {
    extend: {
      // todos los colores vienen de las variables de :root (styles.scss) --
      // un solo sitio para cambiar la paleta, nunca un hex suelto en un
      // componente
      colors: {
        bg: 'var(--bg)',
        panel: 'var(--panel)',
        'panel-dark': 'var(--panel-dark)',
        fg: 'var(--fg)',
        'fg-on-dark': 'var(--fg-on-dark)',
        'fg-muted': 'var(--fg-muted)',
        border: 'var(--border)',
        accent: 'var(--accent)',
        'accent-fg': 'var(--accent-fg)',
        'accent-weak': 'var(--accent-weak)',
        ok: 'var(--ok)',
        'ok-bg': 'var(--ok-bg)',
        warn: 'var(--warn)',
        'warn-bg': 'var(--warn-bg)',
        'warn-border': 'var(--warn-border)',
        bad: 'var(--bad)',
        'bad-bg': 'var(--bad-bg)',
        long: 'var(--long)',
        'long-bg': 'var(--long-bg)',
        short: 'var(--short)',
        'short-bg': 'var(--short-bg)',
        'short-fill': 'var(--short-fill)',
        // categorias de mercado (cripto/accion/materia prima/divisa/indice)
        // -- paleta pastel aparte de la de estado (ok/warn/bad)
        'cat-cripto': 'var(--accent-weak)',
        'cat-accion': '#fde7c7',
        'cat-materia-prima': '#e3d5f8',
        'cat-divisa': '#d6ecff',
        'cat-indice': '#ffe0e0',
      },
      borderRadius: {
        pill: '999px',
        card: '20px',
      },
      boxShadow: {
        card: 'var(--shadow)',
      },
      // padding estandar de una "caja panel" (trader-card, etc.) -- p-panel
      // en vez de repetir p-[18px] suelto en cada sitio
      spacing: {
        panel: '18px',
      },
      // UNA sola tipografia en toda la app -- Poppins, sin monoespaciada
      // para datos (pedido explícito, a diferencia de la app vieja)
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        display: ['Inter', 'system-ui', 'sans-serif'],
      },
      // escala tipografica unica de la app: base 15px, chico 13/14px,
      // grande 20px -- nunca un text-[Nrem] suelto en un componente
      fontSize: {
        xs: '0.8125rem', // 13px -- labels, badges, etiquetas pequeñas
        sm: '0.875rem', // 14px -- texto secundario
        base: '0.9375rem', // 15px -- texto normal, en todas partes
        lg: '1.25rem', // 20px -- titulos y enfasis
      },
    },
  },
  plugins: [],
}
