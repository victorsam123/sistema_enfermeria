// Días calendario inclusivos mediante UTC: independiente de zona y horario de verano.
const vacationStart = document.getElementById('fecha_inicio');
const vacationEnd = document.getElementById('fecha_termino');
const vacationTotal = document.getElementById('total_dias');
if (vacationStart && vacationEnd && vacationTotal) {
  const rangeError = 'La fecha de término no puede ser anterior a la fecha de inicio.';
  function parseCalendarDate(value) {
    const match = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(value);
    if (!match) return null;
    const [, day, month, year] = match.map(Number);
    const date = new Date(0);
    date.setUTCFullYear(year, month - 1, day);
    if (year < 1 || date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1
        || date.getUTCDate() !== day) return null;
    return date.getTime();
  }
  function updateVacationTotal() {
    if (vacationEnd.validationMessage === rangeError) vacationEnd.setCustomValidity('');
    const start = parseCalendarDate(vacationStart.value);
    const end = parseCalendarDate(vacationEnd.value);
    vacationTotal.value = '';
    if (start === null || end === null) return;
    if (end < start) {
      vacationEnd.setCustomValidity(rangeError);
      return;
    }
    vacationTotal.value = String((end - start) / 86400000 + 1);
  }
  vacationStart.addEventListener('input', updateVacationTotal);
  vacationEnd.addEventListener('input', updateVacationTotal);
  updateVacationTotal();
  window.addEventListener('pageshow', updateVacationTotal);
}
