// Días inclusivos sin depender de zona horaria ni horario de verano.
const restStart = document.getElementById('fecha_desde');
const restEnd = document.getElementById('fecha_hasta');
const restTotal = document.getElementById('total_dias');
if (restStart && restEnd && restTotal) {
  const rangeError = 'La fecha hasta no puede ser anterior a la fecha desde.';
  function parseRestDate(value) {
    const match = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(value);
    if (!match) return null;
    const [, day, month, year] = match.map(Number);
    const date = new Date(0);
    date.setUTCFullYear(year, month - 1, day);
    if (year < 1 || date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1
        || date.getUTCDate() !== day) return null;
    return date.getTime();
  }
  function updateRestTotal() {
    if (restEnd.validationMessage === rangeError) restEnd.setCustomValidity('');
    const start = parseRestDate(restStart.value);
    const end = parseRestDate(restEnd.value);
    restTotal.value = '';
    if (start === null || end === null) return;
    if (end < start) { restEnd.setCustomValidity(rangeError); return; }
    restTotal.value = String((end - start) / 86400000 + 1);
  }
  restStart.addEventListener('input', updateRestTotal);
  restEnd.addEventListener('input', updateRestTotal);
  updateRestTotal();
  window.addEventListener('pageshow', updateRestTotal);
}
