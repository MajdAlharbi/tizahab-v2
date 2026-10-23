/** Compile the project's existing Tailwind utilities; no browser runtime. */
module.exports = {
  content: ["./templates/**/*.html", "./static/js/**/*.js", "!./static/js/vendor/**"],
  theme: {extend: {
    colors: {brand: "var(--tz-violet)", "brand-dark": "var(--tz-deep)", "brand-light": "var(--tz-lavender)", accent: "var(--tz-teal)"},
    fontFamily: {sans: ["Inter", "Noto Sans Arabic", "sans-serif"], arimo: ["Inter", "sans-serif"], cantata: ["Inter", "sans-serif"], bona: ["Noto Sans Arabic", "sans-serif"]}
  }},
  plugins: []
};
