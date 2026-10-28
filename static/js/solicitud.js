(() => {
  const form = document.querySelector('[data-solicitud-form]');
  if (!form) return;
  function conditional(name, active) {
    const input = form.elements.namedItem(name);
    const container = input.closest('.alta-upload') || input.closest('.alta-field');
    container.hidden = !active;
    input.disabled = !active;
    input.required = active;
    const label = input.closest('.alta-field').querySelector('label');
    label.querySelector('.alta-optional')?.remove();
    if (!label.querySelector('.alta-required')) {
      const star = document.createElement('span'); star.className = 'alta-required'; star.textContent = '*'; star.setAttribute('aria-label', 'obligatorio'); label.append(star);
    }
  }
  function person(prefix) {
    const human = form.elements.namedItem(prefix + '_tipo').value === 'HUMANA';
    conditional(prefix + '_dni', human);
    conditional(prefix + '_cuit', !human);
  }
  for (const prefix of ['propietario', 'titular']) {
    form.elements.namedItem(prefix + '_tipo').addEventListener('change', () => person(prefix));
    person(prefix);
  }
  function representative() {
    const active = form.elements.namedItem('solicitante_condicion').value === 'APODERADO';
    conditional('dni_apoderado', active);
    conditional('poder_apoderado', active);
  }
  form.elements.namedItem('solicitante_condicion').addEventListener('change', representative);
  representative();
  const files = [...form.querySelectorAll('input[type="file"]')];
  function checkSize() {
    let total = 0;
    for (const input of files) {
      input.setCustomValidity('');
      if (input.disabled) continue;
      for (const file of input.files) {
        total += file.size;
        if (file.size > 5 * 1024 * 1024) input.setCustomValidity('Cada archivo puede pesar hasta 5 MB.');
      }
    }
    if (total > 15 * 1024 * 1024) files.find(input => !input.disabled)?.setCustomValidity('Los adjuntos pueden sumar hasta 15 MB en total.');
  }
  files.forEach(input => input.addEventListener('change', checkSize));
  form.elements.namedItem('solicitante_condicion').addEventListener('change', checkSize);
})();
