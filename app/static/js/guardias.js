const guardiaForm = document.getElementById('guardia-form');
if (guardiaForm) {
  const extraDates = document.getElementById('additional-dates');
  const rowTemplate = document.getElementById('guardia-date-template');
  const message = document.getElementById('guardia-detail-error');
  const applicantField = document.getElementById('solicitante');
  const substituteField = document.getElementById('reemplazante');
  let nextIndex = Math.max(...Array.from(guardiaForm.querySelectorAll('[data-guardia-index]'), row => Number(row.dataset.guardiaIndex))) + 1;

  function updateNamesAndCount() {
    guardiaForm.querySelectorAll('select[data-participant]').forEach(select => {
      for (const option of select.options) {
        option.textContent = option.value === 'S'
          ? `Solicitante (S)${applicantField.value ? ': ' + applicantField.value : ''}`
          : `Reemplazante (R)${substituteField.value ? ': ' + substituteField.value : ''}`;
      }
    });
    document.getElementById('guardia-date-count').textContent = `Filas de fechas: ${guardiaForm.querySelectorAll('[data-guardia-index]').length}`;
    message.hidden = true;
  }

  function bindNewCalendar(row) {
    const picker = row.querySelector('[data-date-for]');
    const field = document.getElementById(picker.dataset.dateFor);
    function validateDate() {
      field.setCustomValidity('');
      if (!field.value) { picker.value = ''; return; }
      const match = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(field.value);
      if (!match) { field.setCustomValidity('Escribe una fecha válida con el formato DD/MM/AAAA.'); return; }
      const [, day, month, year] = match.map(Number);
      const date = new Date(0);
      date.setUTCFullYear(year, month - 1, day);
      if (year < 1 || date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) {
        field.setCustomValidity('Selecciona una fecha válida.'); return;
      }
      picker.value = `${String(year).padStart(4, '0')}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    }
    picker.addEventListener('change', () => {
      if (picker.value) {
        const [year, month, day] = picker.value.split('-');
        field.value = `${day}/${month}/${year}`;
        field.dispatchEvent(new Event('input', { bubbles: true }));
      }
    });
    field.addEventListener('input', validateDate);
    validateDate();
  }

  function initializeRow(row, added = false) {
    if (added) bindNewCalendar(row);
    const start = row.querySelector('[data-hour-start]');
    const end = row.querySelector('[data-hour-end]');
    const validateTime = () => end.setCustomValidity(start.value && start.value === end.value
      ? 'Las horas de inicio y finalización deben ser distintas.' : '');
    start.addEventListener('input', validateTime);
    end.addEventListener('input', validateTime);
    validateTime();
    row.querySelector('[data-remove-date]')?.addEventListener('click', () => {
      row.remove();
      updateNamesAndCount();
    });
  }

  guardiaForm.querySelectorAll('[data-guardia-index]').forEach(row => initializeRow(row));
  document.getElementById('add-guardia-date').addEventListener('click', () => {
    const content = rowTemplate.innerHTML.replaceAll('__index__', String(nextIndex++));
    const container = document.createElement('div');
    // El contenido procede exclusivamente del template estático del servidor.
    container.innerHTML = content;
    const row = container.firstElementChild;
    extraDates.append(row);
    initializeRow(row, true);
    updateNamesAndCount();
    row.querySelector('select[data-participant]').focus();
  });
  applicantField.addEventListener('input', updateNamesAndCount);
  substituteField.addEventListener('input', updateNamesAndCount);
  guardiaForm.addEventListener('input', () => { message.hidden = true; });
  guardiaForm.addEventListener('submit', event => {
    const seen = new Set();
    for (const row of guardiaForm.querySelectorAll('[data-guardia-index]')) {
      const key = JSON.stringify([
        row.querySelector('[data-participant]').value,
        row.querySelector('input[name$="-fecha_guardia"]').value,
        row.querySelector('[data-hour-start]').value,
        row.querySelector('[data-hour-end]').value,
        row.querySelector('[data-code]').value,
      ]);
      if (seen.has(key)) {
        event.preventDefault();
        event.stopImmediatePropagation();
        message.textContent = 'Hay filas con el mismo funcionario, fecha, horario y código. Revisa las fechas antes de guardar.';
        message.hidden = false;
        row.querySelector('input[name$="-fecha_guardia"]').focus();
        return;
      }
      seen.add(key);
    }
  }, true);
  updateNamesAndCount();
}
