(() => {
  const root = document.documentElement;
  root.classList.add('js');
  let theme;
  let sidebar;
  try {
    theme = localStorage.getItem('gger.theme');
    sidebar = localStorage.getItem('gger.sidebar');
  } catch (_) { /* El sitio sigue funcionando con almacenamiento deshabilitado. */ }
  root.dataset.theme = ['light', 'dark'].includes(theme) ? theme :
    (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  root.dataset.sidebar = sidebar === 'collapsed' ? 'collapsed' : 'expanded';
})();
