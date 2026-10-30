'use strict';
document.querySelectorAll('[data-employment-form]').forEach(form => {
  const date = form.elements.namedItem('fecha_ingreso'), year = document.getElementById('employment-year');
  const tenure = document.getElementById('employment-tenure'), reference = form.querySelector('[data-employment-date]');
  let sequence = 0, timer;
  const update = async () => {
    const value = date.value, requestNumber = ++sequence;
    year.value = employeeEntryYear(value); tenure.textContent = 'Selecciona una fecha completa';
    if (!year.value) return;
    tenure.textContent = 'Calculando antigüedad…';
    try {
      const response = await fetch(form.dataset.previewUrl, {method:'POST',credentials:'same-origin',
        headers:{'Content-Type':'application/json','X-CSRFToken':form.elements.namedItem('csrf_token').value},
        body:JSON.stringify({fecha_ingreso:value})});
      if (requestNumber !== sequence || date.value !== value) return;
      if (!response.ok) { tenure.textContent = 'Revisa la fecha de ingreso o recarga el formulario.'; return; }
      const data = await response.json();
      if (requestNumber !== sequence || date.value !== value) return;
      year.value = data.anio_ingreso;
      tenure.textContent = `${data.anios} años, ${data.meses} meses y ${data.dias} días`;
      reference.textContent = `Cálculo al ${data.fecha_consulta} · America/Asuncion`;
    } catch (error) { if (requestNumber === sequence) tenure.textContent = 'La antigüedad se verificará al guardar.'; }
  };
  date.addEventListener('input', () => { sequence++; clearTimeout(timer); timer = setTimeout(update,250); });
});
