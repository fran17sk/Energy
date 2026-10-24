(() => {
  const root = document.documentElement;
  const sidebar = document.getElementById('app-navigation');
  const workspace = document.querySelector('.ui-workspace');
  const toggle = document.querySelector('.ui-menu-toggle');
  const close = document.querySelector('.ui-mobile-close');
  const backdrop = document.querySelector('.ui-backdrop');
  const collapse = document.querySelector('.ui-collapse');
  const theme = document.querySelector('.ui-theme-toggle');
  const mobile = window.matchMedia('(max-width: 1023px)');
  const systemTheme = window.matchMedia('(prefers-color-scheme: dark)');
  let drawerOpen = false;
  const store = (key, value) => { try { localStorage.setItem(key, value); } catch (_) {} };
  const read = key => { try { return localStorage.getItem(key); } catch (_) { return null; } };

  function updateTheme(value) {
    root.dataset.theme = value;
    const dark = value === 'dark';
    theme.setAttribute('aria-label', dark ? 'Activar modo claro' : 'Activar modo oscuro');
    theme.title = theme.getAttribute('aria-label');
    theme.setAttribute('aria-pressed', String(dark));
    document.querySelector('meta[name="theme-color"]').content = dark ? '#101923' : '#f4f7fb';
  }
  function updateSidebar(value) {
    root.dataset.sidebar = value;
    const collapsed = value === 'collapsed';
    collapse.setAttribute('aria-expanded', String(!collapsed));
    collapse.setAttribute('aria-label', collapsed ? 'Expandir menú' : 'Colapsar menú');
    collapse.title = collapse.getAttribute('aria-label');
    collapse.querySelector('span').textContent = collapse.getAttribute('aria-label');
  }
  function drawer(open, restoreFocus = true) {
    drawerOpen = open && mobile.matches;
    root.classList.toggle('ui-drawer-open', drawerOpen);
    backdrop.hidden = !drawerOpen;
    toggle.setAttribute('aria-expanded', String(drawerOpen));
    toggle.setAttribute('aria-label', drawerOpen ? 'Cerrar menú de navegación' : 'Abrir menú de navegación');
    sidebar.inert = mobile.matches && !drawerOpen;
    workspace.inert = drawerOpen;
    if (drawerOpen) {
      sidebar.setAttribute('role', 'dialog');
      sidebar.setAttribute('aria-modal', 'true');
      close.focus();
    } else {
      sidebar.removeAttribute('role');
      sidebar.removeAttribute('aria-modal');
      if (restoreFocus && mobile.matches) toggle.focus();
    }
  }
  theme.addEventListener('click', () => {
    const value = root.dataset.theme === 'dark' ? 'light' : 'dark';
    updateTheme(value);
    store('gger.theme', value);
  });
  collapse.addEventListener('click', () => {
    const value = root.dataset.sidebar === 'collapsed' ? 'expanded' : 'collapsed';
    updateSidebar(value);
    store('gger.sidebar', value);
  });
  toggle.addEventListener('click', () => drawer(!drawerOpen));
  close.addEventListener('click', () => drawer(false));
  backdrop.addEventListener('click', () => drawer(false));
  sidebar.querySelectorAll('a').forEach(link => link.addEventListener('click', () => {
    if (drawerOpen) drawer(false);
  }));
  document.addEventListener('keydown', event => {
    if (!drawerOpen) return;
    if (event.key === 'Escape') { event.preventDefault(); drawer(false); }
    if (event.key === 'Tab') {
      const items = [...sidebar.querySelectorAll('a, button')].filter(el => el.getClientRects().length && !el.disabled);
      const first = items[0]; const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  });
  mobile.addEventListener('change', () => {
    const focusInside = sidebar.contains(document.activeElement);
    drawer(false, false);
    if (mobile.matches && focusInside) toggle.focus();
  });
  systemTheme.addEventListener('change', event => {
    if (!['light', 'dark'].includes(read('gger.theme'))) updateTheme(event.matches ? 'dark' : 'light');
  });
  window.addEventListener('storage', event => {
    if (event.key === 'gger.theme' || event.key === null) {
      const value = read('gger.theme');
      updateTheme(['light', 'dark'].includes(value) ? value : (systemTheme.matches ? 'dark' : 'light'));
    }
    if (event.key === 'gger.sidebar' || event.key === null) updateSidebar(read('gger.sidebar') === 'collapsed' ? 'collapsed' : 'expanded');
  });
  updateTheme(root.dataset.theme);
  updateSidebar(root.dataset.sidebar);
  drawer(false, false);
})();
