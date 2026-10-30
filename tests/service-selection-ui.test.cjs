const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../app/static/js/service_selection.js'), 'utf8');

function page(selected = '0') {
  const handlers = {};
  const button = { name: 'guardar' };
  const selector = { value: selected, options: ['0', '1', '7'].map(value => ({ value,
    cloneNode() { return { value: this.value }; } })) };
  const choice = { value: '', options: [], replaceChildren() { this.options = []; },
    appendChild(option) { this.options.push(option); }, focus() { this.focused = true; } };
  const dialog = { opened: false, showModal() { this.opened = true; }, close() { this.opened = false; },
    addEventListener(type, fn) { handlers['dialog-' + type] = fn; } };
  const confirmation = { addEventListener(type, fn) { handlers.confirm = fn; } };
  const cancel = { addEventListener(type, fn) { handlers.cancel = fn; } };
  const form = { fields: { nombre: 'Datos ingresados', fecha: '04/10/2026' }, submissions: [],
    querySelector() { return selector; }, requestSubmit(submitter) { this.submissions.push(submitter); },
    addEventListener(type, fn, capture) { handlers.submit = fn; handlers.capture = capture; } };
  vm.runInNewContext(source, { document: {
    getElementById(id) { return { 'service-dialog': dialog, 'service-confirm-choice': choice,
      'service-confirmation': confirmation, 'service-cancel': cancel }[id]; },
    querySelectorAll() { return [form]; },
  } });
  const event = { submitter: button, prevented: false, stopped: false,
    preventDefault() { this.prevented = true; }, stopImmediatePropagation() { this.stopped = true; } };
  return { handlers, form, selector, choice, dialog, button, event };
}

test('Sin servicio se abre el selector y no se envía ni se borra el formulario', () => {
  const p = page();
  p.handlers.submit(p.event);
  assert.equal(p.event.prevented, true);
  assert.equal(p.event.stopped, true);
  assert.equal(p.handlers.capture, true);
  assert.equal(p.dialog.opened, true);
  assert.equal(p.choice.focused, true);
  assert.deepEqual(p.choice.options.map(o => o.value), ['', '1', '7']);
  assert.equal(p.form.submissions.length, 0);
  assert.equal(p.form.fields.nombre, 'Datos ingresados');
});

test('Confirmar conserva el botón de envío y asigna un servicio real', () => {
  const p = page();
  p.handlers.submit(p.event);
  p.choice.value = '7';
  p.handlers.confirm(p.event);
  assert.equal(p.selector.value, '7');
  assert.deepEqual(p.form.submissions, [p.button]);
  assert.equal(p.dialog.opened, false);
});

test('Cancelar o Escape conserva los campos y no guarda', () => {
  const p = page();
  p.handlers.submit(p.event);
  p.handlers.cancel();
  p.handlers['dialog-close']();
  p.choice.value = '1';
  p.handlers.confirm(p.event);
  assert.equal(p.selector.value, '0');
  assert.equal(p.form.submissions.length, 0);
  assert.equal(p.form.fields.fecha, '04/10/2026');
});

test('Con servicio elegido el envío continúa hacia las validaciones existentes', () => {
  const p = page('1');
  p.handlers.submit(p.event);
  assert.equal(p.event.prevented, false);
  assert.equal(p.event.stopped, false);
  assert.equal(p.dialog.opened, false);
});
