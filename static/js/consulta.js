(() => {
  const notice = document.getElementById('consulta-no-encontrado');
  if (notice && window.Swal) {
    window.Swal.fire({
      icon: 'info',
      title: 'No encontramos tu trámite',
      text: 'Revisá que el número de trámite, el NIS y el DNI / CUIT coincidan con los de tu solicitud e intentá nuevamente.',
      confirmButtonText: 'Revisar datos',
      confirmButtonColor: '#1778f2',
      customClass: { popup: 'consulta-alert' },
      returnFocus: false,
    }).then(() => document.getElementById('id_numero')?.focus());
  }
  const current = document.querySelector('.consulta-step.current');
  const viewport = document.querySelector('.consulta-timeline-viewport');
  if (current && viewport && window.matchMedia('(min-width: 641px)').matches) {
    viewport.scrollLeft = current.offsetLeft - viewport.offsetLeft - (viewport.clientWidth - current.clientWidth) / 2;
  }
})();
