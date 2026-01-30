/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            colors: {
                background: 'var(--background)',
                foreground: 'var(--foreground)',
                border: 'var(--border)',
                primary: 'var(--primary)',
                success: 'var(--success)',
                warning: 'var(--warning)',
                error: 'var(--error)',
                surface: 'var(--surface)',
                'muted-foreground': 'var(--muted-foreground)',
            },
            fontFamily: {
                primary: ['Space Grotesk', 'sans-serif'],
                secondary: ['Inter', 'sans-serif'],
            },
        },
    },
    plugins: [],
}
