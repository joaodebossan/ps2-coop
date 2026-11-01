/* Tema claro / escuro / sistema. Carregado antes do body para evitar flash. */
(() => {
  const KEY = "ps2coop-theme";
  const media = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;

  function stored() {
    try {
      const value = localStorage.getItem(KEY);
      return value === "light" || value === "dark" || value === "system" ? value : "system";
    } catch {
      return "system";
    }
  }

  function resolved(mode) {
    if (mode === "light" || mode === "dark") return mode;
    return media && media.matches ? "dark" : "light";
  }

  function apply(mode, persist) {
    const value = mode === "light" || mode === "dark" ? mode : "system";
    const effective = resolved(value);
    document.documentElement.dataset.theme = effective;
    document.documentElement.dataset.themeMode = value;
    document.documentElement.style.colorScheme = effective;
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", effective === "dark" ? "#24252c" : "#e5e8ed");
    if (persist) {
      try {
        localStorage.setItem(KEY, value);
      } catch {
        /* sem localStorage: o tema vale só nesta página */
      }
    }
    window.dispatchEvent(new CustomEvent("ps2coop-theme", { detail: { mode: value, theme: effective } }));
  }

  window.PS2Theme = {
    get mode() {
      return stored();
    },
    get theme() {
      return resolved(stored());
    },
    set(mode) {
      apply(mode, true);
    },
    refresh() {
      apply(stored(), false);
    },
  };

  apply(stored(), false);
  if (media) {
    const onChange = () => {
      if (stored() === "system") apply("system", false);
    };
    if (media.addEventListener) media.addEventListener("change", onChange);
    else if (media.addListener) media.addListener(onChange);
  }
})();
