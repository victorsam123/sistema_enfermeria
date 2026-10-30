const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

test('Contraseñas individuales se muestran y ocultan sin cambiar su contenido', () => {
  const field = { type: 'password', value: 'ContraseñaDePrueba2026!' };
  const attributes = {};
  const icon = {};
  let click;
  const button = { dataset: { passwordToggle: 'password' },
    addEventListener(type, handler) { click = handler; },
    setAttribute(name, value) { attributes[name] = value; }, querySelector() { return icon; } };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../app/static/js/user_accounts.js'), 'utf8'), {
    document: { querySelectorAll: () => [button], getElementById: () => field },
  });
  click();
  assert.equal(field.type, 'text');
  assert.equal(attributes['aria-pressed'], 'true');
  assert.equal(attributes['aria-label'], 'Ocultar contraseña');
  click();
  assert.equal(field.type, 'password');
  assert.equal(field.value, 'ContraseñaDePrueba2026!');
  assert.equal(attributes['aria-pressed'], 'false');
});

test('La vista autorizada de impresión requiere una acción explícita', () => {
  let handler;
  let printed = 0;
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../app/static/js/print_record.js'), 'utf8'), {
    document: { getElementById: () => ({ addEventListener(type, callback) { handler = callback; } }) },
    window: { print() { printed++; } },
  });
  assert.equal(printed, 0);
  handler();
  assert.equal(printed, 1);
});
