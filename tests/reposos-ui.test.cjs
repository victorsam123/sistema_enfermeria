const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const selectors = fs.readFileSync(path.join(__dirname, '../app/static/js/administration.js'), 'utf8');
const reposos = fs.readFileSync(path.join(__dirname, '../app/static/js/reposos.js'), 'utf8');

function input(value = '') {
  return { value, validationMessage: '', listeners: {},
    setCustomValidity(message) { this.validationMessage = message; },
    addEventListener(type, fn) { (this.listeners[type] ??= []).push(fn); },
    dispatchEvent(event) { for (const fn of this.listeners[event.type] || []) fn(event); },
  };
}

function page(start, end) {
  const fields = { fecha_desde: input(start), fecha_hasta: input(end),
    fecha_entrega_departamento: input('03/10/2026'), total_dias: input() };
  const pickers = ['fecha_desde', 'fecha_hasta', 'fecha_entrega_departamento']
    .map(id => Object.assign(input(), { dataset: { dateFor: id } }));
  const context = vm.createContext({
    document: { getElementById: id => fields[id],
      querySelectorAll: selector => selector === '[data-date-for]' ? pickers : [] },
    window: { addEventListener() {} }, Event: class { constructor(type) { this.type = type; } },
  });
  vm.runInContext(selectors, context);
  vm.runInContext(reposos, context);
  return { fields, pickers };
}

for (const [start, end, total] of [
  ['01/10/2026', '02/10/2026', '2'], ['16/10/2026', '29/10/2026', '14'],
  ['01/10/2026', '01/10/2026', '1'], ['28/02/2028', '01/03/2028', '3'],
  ['31/12/2026', '01/01/2027', '2'],
]) {
  test(`Reposo del ${start} al ${end}: ${total} días`, () => {
    assert.equal(page(start, end).fields.total_dias.value, total);
  });
}

test('Calendario de reposo recalcula y rechaza fechas invertidas', () => {
  const { fields, pickers } = page('01/10/2026', '02/10/2026');
  pickers[1].value = '2026-10-14'; pickers[1].dispatchEvent({ type: 'change' });
  assert.equal(fields.total_dias.value, '14');
  fields.fecha_desde.value = '15/10/2026'; fields.fecha_desde.dispatchEvent({ type: 'input' });
  assert.equal(fields.total_dias.value, '');
  assert.match(fields.fecha_hasta.validationMessage, /no puede ser anterior/);
  fields.fecha_desde.value = '01/10/2026'; fields.fecha_desde.dispatchEvent({ type: 'input' });
  assert.equal(fields.total_dias.value, '14');
  assert.equal(fields.fecha_hasta.validationMessage, '');
});

test('Fechas inválidas o incompletas no generan total y entrega también se valida', () => {
  assert.equal(page('31/02/2026', '15/03/2026').fields.total_dias.value, '');
  const { fields } = page('01/10/2026', '');
  assert.equal(fields.total_dias.value, '');
  fields.fecha_entrega_departamento.value = '31/02/2026';
  fields.fecha_entrega_departamento.dispatchEvent({ type: 'input' });
  assert.match(fields.fecha_entrega_departamento.validationMessage, /fecha válida/);
});
