// Selectores nativos con un campo visible que conserva DD/MM/AAAA.
document.querySelectorAll('[data-date-for]').forEach((picker) => {
  const field = document.getElementById(picker.dataset.dateFor);
  function syncDate() {
    field.setCustomValidity('');
    if (!field.value) { picker.value = ''; return; }
    const match = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(field.value);
    if (!match) {
      field.setCustomValidity('Escribe una fecha válida con el formato DD/MM/AAAA.');
      return;
    }
    const [, day, month, year] = match;
    const date = new Date(0);
    date.setUTCFullYear(Number(year), Number(month) - 1, Number(day));
    if (Number(year) < 1 || date.getUTCFullYear() !== Number(year)
        || date.getUTCMonth() !== Number(month) - 1 || date.getUTCDate() !== Number(day)) {
      field.setCustomValidity('Selecciona una fecha válida.');
      return;
    }
    picker.value = `${year}-${month}-${day}`;
  }
  picker.addEventListener('change', () => {
    if (picker.value) {
      const [year, month, day] = picker.value.split('-');
      field.value = `${day}/${month}/${year}`;
      field.dispatchEvent(new Event('input', { bubbles: true }));
    }
  });
  field.addEventListener('input', syncDate);
  syncDate();
});

const applicant = document.getElementById('solicitante');
const substitute = document.getElementById('reemplazante');
if (applicant && substitute) {
  const nameKey = value => value.normalize('NFKC').trim().replace(/\s+/g, ' ').toLocaleLowerCase('es');
  const validateParticipants = () => {
    substitute.setCustomValidity(applicant.value && nameKey(applicant.value) === nameKey(substitute.value)
      ? 'El solicitante y el reemplazante deben ser personas distintas.' : '');
  };
  applicant.addEventListener('input', validateParticipants);
  substitute.addEventListener('input', validateParticipants);
  validateParticipants();
}
const startTime = document.getElementById('hora_inicio');
const endTime = document.getElementById('hora_fin');
if (startTime && endTime) {
  const validateTimes = () => endTime.setCustomValidity(startTime.value && startTime.value === endTime.value
    ? 'Las horas de inicio y finalización deben ser distintas.' : '');
  startTime.addEventListener('input', validateTimes);
  endTime.addEventListener('input', validateTimes);
  validateTimes();
}

document.querySelectorAll('.administrative-form').forEach((form) => {
  form.addEventListener('submit', (event) => {
    if (form.dataset.submitting === 'true') { event.preventDefault(); return; }
    form.dataset.submitting = 'true';
    form.querySelector('button[type="submit"]').disabled = true;
  });
  window.addEventListener('pageshow', () => {
    delete form.dataset.submitting;
    form.querySelector('button[type="submit"]').disabled = false;
  });
});
