(() => {
  const toggle = document.querySelector('.login-toggle');
  const password = document.getElementById(toggle?.getAttribute('aria-controls'));
  if (!toggle || !password) return;
  toggle.hidden = false;
  toggle.addEventListener('click', () => {
    const visible = password.type === 'password';
    password.type = visible ? 'text' : 'password';
    toggle.textContent = visible ? 'Ocultar' : 'Mostrar';
    toggle.setAttribute('aria-pressed', String(visible));
  });
})();
