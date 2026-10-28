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
  const ownerCopy = document.getElementById('copiar-propietario');
  const applicantCopy = document.getElementById('copiar-solicitante');
  const value = name => form.elements.namedItem(name);
  function syncCopies() {
    if (ownerCopy.checked) {
      for (const field of ['tipo', 'nombre', 'dni', 'cuit']) {
        value('titular_' + field).value = value('propietario_' + field).value;
        value('titular_' + field).readOnly = field !== 'tipo';
      }
      person('titular');
    } else {
      for (const field of ['nombre', 'dni', 'cuit']) value('titular_' + field).readOnly = false;
    }
    const canCopy = value('titular_tipo').value === 'HUMANA' && value('solicitante_condicion').value === 'TITULAR';
    document.getElementById('copiar-solicitante-label').hidden = !canCopy;
    if (!canCopy) applicantCopy.checked = false;
    for (const field of ['nombre', 'dni']) {
      const input = value('solicitante_' + field);
      input.readOnly = applicantCopy.checked;
      if (applicantCopy.checked) input.value = value('titular_' + field).value;
    }
  }
  ownerCopy.addEventListener('change', syncCopies);
  applicantCopy.addEventListener('change', syncCopies);
  form.addEventListener('input', event => {
    if (event.target.name?.startsWith('propietario_')) syncCopies();
    if (event.target.name?.startsWith('titular_')) {
      if (event.target.name === 'titular_tipo') ownerCopy.checked = false;
      syncCopies();
    }
  });
  form.addEventListener('change', event => {
    if (['propietario_tipo', 'titular_tipo', 'solicitante_condicion'].includes(event.target.name)) syncCopies();
  });
  syncCopies();
  // Explain native validation failures, including fields outside the current viewport.
  const validation = form.querySelector('.solicitud-validation');
  form.addEventListener('invalid', event => {
    validation.hidden = false;
    validation.textContent = 'Completá o corregí los campos señalados antes de revisar el envío. ' + event.target.validationMessage;
  }, true);
  const errors = form.querySelector('.alta-error-summary');
  if (errors) { errors.tabIndex = -1; errors.focus(); }
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
