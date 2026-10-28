(() => {
  const descriptions = document.getElementById('confirmaciones-data');
  const actions = descriptions ? JSON.parse(descriptions.textContent) : {};
  const fallback = {
    solicitud_email: { titulo: 'Enviar solicitud de factibilidad a EDESA', resultado: 'Se enviarán todos los datos y adjuntos al correo designado por EDESA. Se creará un código y un registro mínimo de seguimiento. La presentación completa y los adjuntos iniciales no se guardarán en la aplicación.' },
    alta: { titulo: 'Registrar solicitud de factibilidad', resultado: 'Se creará tu trámite en EDESA y se enviará el código de seguimiento al correo indicado. Guardá ese código para consultar el expediente.' },
    proyecto: { titulo: 'Enviar Proyecto Ejecutivo', resultado: 'Se incorporará el proyecto al expediente y EDESA tendrá una tarea pendiente de recepción y revisión.' },
    correo: { titulo: 'Reintentar notificación por correo', resultado: 'Se intentará enviar nuevamente esta notificación al titular. Si el servidor la acepta, se aplicará el avance que corresponda al trámite.' },
  };
  function summary(form, info) {
    const container = document.createElement('div');
    container.className = 'wf-confirm-summary';
    const intro = document.createElement('p'); intro.textContent = info.resultado; container.append(intro);
    if (form.dataset.confirmKind === 'solicitud_email') {
      for (const section of form.querySelectorAll('[data-solicitud-section]')) {
        const title = document.createElement('h3'); title.className = 'wf-confirm-group-title';
        const legend = section.querySelector('legend').cloneNode(true);
        legend.querySelector('.alta-section-number')?.remove(); title.textContent = legend.textContent.trim();
        container.append(title);
        const list = document.createElement('dl');
        for (const input of section.querySelectorAll('input, select')) {
          if (input.disabled || input.type === 'hidden' || !input.name) continue;
          const label = form.querySelector(`label[for="${input.id}"]`);
          const value = input.type === 'file' ? [...input.files].map(file => file.name).join(', ') :
            (input.tagName === 'SELECT' ? input.selectedOptions[0]?.textContent : input.value);
          if (!value) continue;
          const dt = document.createElement('dt'); dt.textContent = label?.childNodes[0]?.textContent.trim() || input.name;
          const dd = document.createElement('dd'); dd.textContent = value; list.append(dt, dd);
        }
        container.append(list);
      }
    } else {
    const details = document.createElement('dl');
    const row = (label, value) => {
      if (!value) return;
      const dt = document.createElement('dt'); dt.textContent = label;
      const dd = document.createElement('dd'); dd.textContent = value;
      details.append(dt, dd);
    };
    row('Trámite', form.dataset.tramite);
    row('Etapa actual', form.dataset.etapa);
    row('Estado actual', form.dataset.estado);
    row('Organismo', form.dataset.organismo);
    row('Correo para notificaciones', form.dataset.destinatario);
    row('Usuario responsable', form.dataset.usuario);
    row('Notificación', form.dataset.asunto);
    for (const [name, label] of [['titular_nombre','Titular'], ['titular_email','Correo'], ['nis','NIS'], ['expediente','Expediente administrativo'], ['fecha','Fecha y hora (Salta)'], ['observacion','Detalle / indicaciones']]) {
      const input = form.elements.namedItem(name);
      let value = input?.value;
      if (name === 'fecha' && value) {
        const [date, time] = value.split('T');
        value = date.split('-').reverse().join('/') + ' · ' + time;
      }
      row(label, value);
    }
    for (const input of form.querySelectorAll('input[type="file"]')) {
      for (const file of input.files) row('Documento', file.name);
    }
    container.append(details);
    }
    const note = document.createElement('p'); note.className = 'wf-confirm-note';
    note.textContent = form.dataset.usuario ? 'Esta actuación quedará registrada con tu usuario, organismo, fecha y hora.' : 'Revisá los datos y el documento antes de confirmar.';
    container.append(note);
    return container;
  }
  document.querySelectorAll('form[data-confirm-form]').forEach(form => {
    let pending = false;
    let sending = false;
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (pending || sending || !form.reportValidity()) return;
      let info = actions[form.elements.namedItem('accion')?.value] || fallback[form.dataset.confirmKind];
      if (form.dataset.confirmKind === 'correo') {
        const result = { RESPUESTA: 'Se reintentará el correo con la respuesta de factibilidad. Al ser aceptado por el servidor se habilitará la presentación del Proyecto Ejecutivo.', CONVOCATORIA: 'Se reintentará la convocatoria para firmar el contrato. Al ser aceptada por el servidor se habilitará la carga del contrato firmado.' }[form.dataset.evento];
        if (result) info = { ...info, resultado: result };
      }
      if (!info) return;
      // If the bundle fails to load, retain an explicit confirmation rather than silently submit.
      if (!window.Swal) {
        if (!window.confirm(info.titulo + '\n\n' + info.resultado)) return;
      } else {
        pending = true;
        const result = await window.Swal.fire({
          title: info.titulo, html: summary(form, info), icon: 'question',
          showCancelButton: true, confirmButtonText: 'Confirmar y continuar',
          cancelButtonText: 'Volver a revisar', focusCancel: true,
          confirmButtonColor: '#236be5', customClass: { popup: 'wf-confirm-modal' },
          width: 'min(560px, calc(100vw - 32px))',
        });
        pending = false;
        if (!result.isConfirmed) return;
      }
      sending = true;
      form.querySelectorAll('button[type="submit"]').forEach(button => {
        button.disabled = true; button.textContent = form.dataset.confirmKind === 'solicitud_email' ? 'Enviando…' : 'Registrando…';
      });
      HTMLFormElement.prototype.submit.call(form);
    });
    if (form.hasAttribute('data-confirm-on-open')) form.requestSubmit();
  });
})();
