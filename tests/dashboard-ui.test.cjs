const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../app/static/js/app.js'), 'utf8');

function harness() {
  let elapsed = 0;
  const intervals = new Map();
  const elements = {
    'dashboard-clock': { dataset: { epochMs: String(Date.parse('2026-01-01T02:59:59Z')),
      offsetSeconds: '-10800', syncUrl: '/api/reloj' } },
    'dashboard-date': {}, 'dashboard-time': {}, 'module-dialog-title': {},
    'module-dialog': { opened: 0, showModal() { this.opened += 1; } },
  };
  const buttons = ['Justificativo', 'Reposo', 'Cambio de Guardia', 'Vacaciones', 'Comisionados']
    .map(label => ({ dataset: { moduleLabel: label }, addEventListener(type, handler) { this[type] = handler; } }));
  class WrongDeviceDate extends Date {
    static now() { return Date.parse('2099-01-01T00:00:00Z'); }
    getDate() { throw Error('No debe utilizar la zona del dispositivo'); }
    getMonth() { throw Error('No debe utilizar la zona del dispositivo'); }
    getFullYear() { throw Error('No debe utilizar la zona del dispositivo'); }
    getHours() { throw Error('No debe utilizar la zona del dispositivo'); }
  }
  vm.runInNewContext(source, {
    document: { hidden: true, getElementById: id => elements[id],
      querySelectorAll: () => buttons, addEventListener() {} },
    window: { addEventListener() {} }, performance: { now: () => elapsed },
    Date: WrongDeviceDate, setInterval: (fn, delay) => intervals.set(delay, fn),
  });
  return { elements, buttons, intervals, advance(ms) { elapsed += ms; intervals.get(1000)(); } };
}

test('El reloj ignora la hora/zona del dispositivo y cambia la fecha a medianoche', () => {
  const page = harness();
  assert.equal(page.elements['dashboard-date'].textContent, '31/12/2025');
  assert.equal(page.elements['dashboard-time'].textContent, '23:59:59');
  page.advance(1000);
  assert.equal(page.elements['dashboard-date'].textContent, '01/01/2026');
  assert.equal(page.elements['dashboard-time'].textContent, '00:00:00');
  page.advance(7000);
  assert.equal(page.elements['dashboard-time'].textContent, '00:00:07');
  assert.equal(page.elements['dashboard-time'].dateTime, '2026-01-01T00:00:07-03:00');
  assert.ok(page.intervals.has(60000));
});

test('Las cinco tarjetas abren el aviso e identifican el módulo seleccionado', () => {
  const page = harness();
  for (const button of page.buttons) {
    button.click();
    assert.equal(page.elements['module-dialog-title'].textContent, button.dataset.moduleLabel);
  }
  assert.equal(page.elements['module-dialog'].opened, 5);
});
