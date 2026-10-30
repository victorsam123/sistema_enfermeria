const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const administration = fs.readFileSync(path.join(__dirname, '../app/static/js/administration.js'), 'utf8');
const vacations = fs.readFileSync(path.join(__dirname, '../app/static/js/vacaciones.js'), 'utf8');

function input(value = '') {
  return { value, validationMessage: '', listeners: {},
    setCustomValidity(message) { this.validationMessage = message; },
    addEventListener(type, fn) { (this.listeners[type] ??= []).push(fn); },
    dispatchEvent(event) { for (const fn of this.listeners[event.type] || []) fn(event); },
  };
}

function page(start, end) {
  const fields = { fecha_inicio: input(start), fecha_termino: input(end), total_dias: input() };
  const pickers = ['fecha_inicio', 'fecha_termino'].map(id => Object.assign(input(), { dataset: { dateFor: id } }));
  const context = vm.createContext({
    document: { getElementById: id => fields[id],
      querySelectorAll: selector => selector === '[data-date-for]' ? pickers : [] },
    window: { addEventListener() {} }, Event: class { constructor(type) { this.type = type; } },
  });
  vm.runInContext(administration, context);
  vm.runInContext(vacations, context);
  return { fields, pickers };
}

for (const [start, end, total] of [
  ['01/11/2026', '15/11/2026', '15'], ['01/11/2026', '01/11/2026', '1'],
  ['28/02/2028', '01/03/2028', '3'], ['07/11/2026', '08/11/2026', '2'],
  ['31/12/2026', '01/01/2027', '2'],
]) {
  test(`Cálculo inclusivo ${start} a ${end}: ${total} días`, () => {
    assert.equal(page(start, end).fields.total_dias.value, total);
  });
}

test('Cambiar fechas con el calendario actualiza el total y rechaza término anterior', () => {
  const { fields, pickers } = page('01/11/2026', '15/11/2026');
  pickers[1].value = '2026-11-20';
  pickers[1].dispatchEvent({ type: 'change' });
  assert.equal(fields.total_dias.value, '20');
  fields.fecha_inicio.value = '21/11/2026';
  fields.fecha_inicio.dispatchEvent({ type: 'input' });
  assert.equal(fields.total_dias.value, '');
  assert.match(fields.fecha_termino.validationMessage, /no puede ser anterior/);
  fields.fecha_inicio.value = '01/11/2026';
  fields.fecha_inicio.dispatchEvent({ type: 'input' });
  assert.equal(fields.total_dias.value, '20');
  assert.equal(fields.fecha_termino.validationMessage, '');
});

test('Fechas inexistentes o incompletas no producen un total', () => {
  assert.equal(page('31/02/2026', '15/03/2026').fields.total_dias.value, '');
  assert.equal(page('01/11/2026', '').fields.total_dias.value, '');
});
