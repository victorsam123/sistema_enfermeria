const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../app/static/js/administration.js'), 'utf8');

function input(value = '') {
  return { value, validityMessage: '', listeners: {},
    setCustomValidity(message) { this.validityMessage = message; },
    addEventListener(event, handler) { this.listeners[event] = handler; },
    dispatchEvent(event) { this.listeners[event.type]?.(event); },
  };
}

function page() {
  const fields = { fecha_cambio: input('29/02/2028'), solicitante: input('Ana López'),
    reemplazante: input('Luis Gómez'), hora_inicio: input('18:00'), hora_fin: input('06:00') };
  const picker = input();
  picker.dataset = { dateFor: 'fecha_cambio' };
  const submit = { disabled: false };
  const form = { dataset: {}, listeners: {}, querySelector: () => submit,
    addEventListener(event, handler) { this.listeners[event] = handler; } };
  const windowEvents = {};
  vm.runInNewContext(source, {
    document: { getElementById: id => fields[id],
      querySelectorAll: selector => selector === '[data-date-for]' ? [picker] : [form] },
    window: { addEventListener: (event, handler) => { windowEvents[event] = handler; } },
    Event: class { constructor(type) { this.type = type; } },
  });
  return { fields, picker, submit, form, windowEvents };
}

test('Calendario mantiene DD/MM/AAAA y rechaza fechas imposibles', () => {
  const { fields, picker } = page();
  assert.equal(picker.value, '2028-02-29');
  fields.fecha_cambio.value = '29/02/2026';
  fields.fecha_cambio.dispatchEvent({ type: 'input' });
  assert.match(fields.fecha_cambio.validityMessage, /fecha válida/);
  picker.value = '2026-10-21';
  picker.dispatchEvent({ type: 'change' });
  assert.equal(fields.fecha_cambio.value, '21/10/2026');
  assert.equal(fields.fecha_cambio.validityMessage, '');
});

test('Validación de participantes y horario permite turnos nocturnos', () => {
  const { fields } = page();
  assert.equal(fields.hora_fin.validityMessage, '');
  fields.reemplazante.value = '  ANA   LÓPEZ  ';
  fields.reemplazante.dispatchEvent({ type: 'input' });
  assert.match(fields.reemplazante.validityMessage, /personas distintas/);
  fields.reemplazante.value = 'Otra Persona';
  fields.reemplazante.dispatchEvent({ type: 'input' });
  assert.equal(fields.reemplazante.validityMessage, '');
  fields.hora_fin.value = '18:00';
  fields.hora_fin.dispatchEvent({ type: 'input' });
  assert.match(fields.hora_fin.validityMessage, /deben ser distintas/);
});

test('Doble clic se bloquea y volver a la página rehabilita el formulario', () => {
  const { form, submit, windowEvents } = page();
  let prevented = false;
  const event = { preventDefault() { prevented = true; } };
  form.listeners.submit(event);
  assert.equal(submit.disabled, true);
  assert.equal(prevented, false);
  form.listeners.submit(event);
  assert.equal(prevented, true);
  windowEvents.pageshow();
  assert.equal(submit.disabled, false);
  assert.equal(form.dataset.submitting, undefined);
});
