'use strict';
function employeeEntryYear(value) {
  const match = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(value);
  if (!match || Number(match[3]) < 1) return '';
  const date = new Date(0); date.setUTCFullYear(Number(match[3]), Number(match[2])-1, Number(match[1]));
  return date.getUTCFullYear() === Number(match[3]) && date.getUTCMonth() === Number(match[2])-1 && date.getUTCDate() === Number(match[1]) ? match[3] : '';
}
if (typeof module !== 'undefined') module.exports = { employeeEntryYear };
if (typeof document !== 'undefined') {
  const entry = document.getElementById('fecha_ingreso'), year = document.getElementById('employee-entry-year');
  if (entry && year) entry.addEventListener('input', () => { year.value = employeeEntryYear(entry.value); });
  document.querySelectorAll('[data-employee-lookup]').forEach(zone => {
    const form = zone.closest('form'), input = zone.querySelector('[data-lookup-cedula]'), result = zone.querySelector('[data-lookup-result]');
    const name = form.elements.namedItem(zone.dataset.targetName), link = form.elements.namedItem(zone.dataset.targetLink);
    const search = zone.querySelector('[data-lookup-search]');
    const clear = () => { link.value = ''; result.textContent = 'Vínculo retirado; el nombre se conserva como texto de la carga.'; };
    zone.querySelector('[data-lookup-clear]')?.addEventListener('click', clear);
    name.addEventListener('input', () => { if (link.value) clear(); });
    search.addEventListener('click', async () => {
      if (!input.value.trim()) { result.textContent = 'Ingresa el número de cédula.'; input.focus(); return; }
      search.disabled = true; result.textContent = 'Buscando funcionario…';
      try {
        const response = await fetch(zone.dataset.endpoint, { method: 'POST', credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': form.elements.namedItem('csrf_token').value },
          body: JSON.stringify({cedula: input.value, contexto: zone.dataset.context}) });
        if (!response.ok) {
          result.textContent = response.status === 429 ? 'Demasiadas búsquedas. Espera un minuto.' : 'No se pudo consultar. Revisa la cédula o recarga el formulario.';
          return;
        }
        const data = await response.json();
        if (!data.encontrado) { result.textContent = data.mensaje; return; }
        name.value = data.nombre_completo; name.dispatchEvent(new Event('input', {bubbles:true}));
        link.value = String(data.id); result.textContent = 'Funcionario encontrado. Nombre completado y ficha vinculada a esta carga.';
      } catch (error) { result.textContent = 'La búsqueda no está disponible. Comprueba tu sesión y conexión.'; }
      finally { search.disabled = false; }
    });
  });
  const profile = document.querySelector('[data-profile-today]'), clock = document.getElementById('dashboard-date');
  if (profile && clock && typeof MutationObserver !== 'undefined') {
    new MutationObserver(() => { if (clock.textContent.trim() !== profile.dataset.profileToday) window.location.reload(); })
      .observe(clock, {subtree:true,childList:true,characterData:true});
  }
}
