const test = require('node:test');
const assert = require('node:assert/strict');
const { employeeEntryYear } = require('../app/static/js/employees.js');
test('Año de ingreso desde fechas completas válidas, incluidos bisiestos', () => {
  assert.equal(employeeEntryYear('10/03/2015'),'2015');
  assert.equal(employeeEntryYear('29/02/2024'),'2024');
});
test('No inventa año ni completa fechas inválidas o parciales', () => {
  for (const value of ['','2026','10/2026','31/02/2026','29/02/2025','15/13/2026','01/01/0000']) assert.equal(employeeEntryYear(value),'');
});
