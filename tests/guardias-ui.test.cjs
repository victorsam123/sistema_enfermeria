const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../app/static/js/guardias.js'), 'utf8');

function field(value = '') {
  return { value, listeners: {}, validationMessage: '', focus() { this.focused = true; },
    setCustomValidity(message) { this.validationMessage = message; },
    addEventListener(event, fn) { this.listeners[event] = fn; } };
}

function page() {
  const rows = [];
  const allFields = {};
  const names = { solicitante: field('Gloria Ejemplo'), reemplazante: field('Nora Ejemplo') };
  function row(index, role = 'S', removable = false) {
    const date = field('');
    const participant = Object.assign(field(role), { options: [{ value: 'S' }, { value: 'R' }] });
    const start = field('18:00'), end = field('06:00'), code = field(role);
    const picker = Object.assign(field(), { dataset: { dateFor: `detalles-${index}-fecha_guardia` } });
    allFields[picker.dataset.dateFor] = date;
    const remove = removable ? field() : null;
    const element = { dataset: { guardiaIndex: String(index) }, participant, date, start, end, code, picker, remove,
      remove() { rows.splice(rows.indexOf(element), 1); },
      querySelector(selector) {
        return ({ '[data-participant]': participant, 'select[data-participant]': participant,
          'input[name$="-fecha_guardia"]': date, '[data-hour-start]': start,
          '[data-hour-end]': end, '[data-code]': code, '[data-date-for]': picker,
          '[data-remove-date]': remove })[selector];
      } };
    return element;
  }
  rows.push(row(0, 'S'), row(1, 'R'));
  const events = {};
  const form = { querySelectorAll(selector) {
    return selector === '[data-guardia-index]' ? rows : rows.slice(2).map(row => row.participant);
  }, addEventListener(event, fn) { events[event] = fn; } };
  const elements = { 'guardia-form': form, 'additional-dates': { append(value) { rows.push(value); } },
    'guardia-date-template': { innerHTML: '__index__' }, 'guardia-detail-error': {},
    'guardia-date-count': {}, 'add-guardia-date': field(), ...names };
  vm.runInNewContext(source, { document: {
    getElementById(id) { return elements[id] || allFields[id]; },
    createElement() { return { set innerHTML(value) { this.firstElementChild = row(Number(value), 'S', true); } }; },
  }, Event: class { constructor(type) { this.type = type; } } });
  return { rows, elements, events, names };
}

test('Agregar fechas no se limita a dos y usa identificadores únicos incluso al quitar borradores', () => {
  const { rows, elements } = page();
  for (let i = 0; i < 10; i++) elements['add-guardia-date'].listeners.click();
  assert.equal(rows.length, 12);
  assert.equal(new Set(rows.map(row => row.dataset.guardiaIndex)).size, 12);
  const removedIndex = rows[5].dataset.guardiaIndex;
  rows[5].querySelector('[data-remove-date]').listeners.click();
  elements['add-guardia-date'].listeners.click();
  assert.equal(rows.length, 12);
  assert.ok(!rows.some(row => row.dataset.guardiaIndex === removedIndex));
  assert.equal(rows.at(-1).dataset.guardiaIndex, '12');
});

test('Fila adicional valida fechas y horarios y conserva los nombres de los participantes', () => {
  const { rows, elements, names } = page();
  elements['add-guardia-date'].listeners.click();
  const added = rows.at(-1);
  assert.match(added.participant.options[0].textContent, /Gloria Ejemplo/);
  names.solicitante.value = 'Nombre Corregido';
  names.solicitante.listeners.input();
  assert.match(added.participant.options[0].textContent, /Nombre Corregido/);
  added.date.value = '02-08/10/2026'; added.date.listeners.input();
  assert.match(added.date.validationMessage, /fecha válida/);
  added.date.value = '08/10/2026'; added.date.listeners.input();
  assert.equal(added.date.validationMessage, '');
  added.end.value = '18:00'; added.end.listeners.input();
  assert.match(added.end.validationMessage, /distintas/);
});

test('Doble fila exacta impide enviar; fechas independientes permiten guardar', () => {
  const { rows, elements, events } = page();
  rows[0].date.value = '02/10/2026'; rows[1].date.value = '08/10/2026';
  elements['add-guardia-date'].listeners.click();
  const added = rows.at(-1);
  added.date.value = '02/10/2026';
  let prevented = false, stopped = false;
  const event = { preventDefault() { prevented = true; }, stopImmediatePropagation() { stopped = true; } };
  events.submit(event);
  assert.equal(prevented, true); assert.equal(stopped, true);
  added.date.value = '17/10/2026';
  prevented = false; events.submit(event);
  assert.equal(prevented, false);
});
