const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/js/novedades.js', 'utf8');

function setup() {
  const ids = ['birthday-dialog', 'birthday-message', 'birthday-send', 'birthday-no-phone',
    'birthday-copy-status', 'birthday-dialog-name', 'birthday-copy', 'birthday-close'];
  const els = Object.fromEntries(ids.map(id => [id, {
    addEventListener(type, fn) { this[type] = fn; },
    setAttribute(key, value) { this[key] = value; },
    removeAttribute(key) { delete this[key]; },
    focus() {}, select() { this.selected = true; },
  }]));
  els['birthday-dialog'].showModal = function () { this.opened = true; };
  els['birthday-dialog'].close = function () { this.opened = false; };
  const page = { dataset: {}, addEventListener(type, fn) { this[type] = fn; } };
  let copied;
  vm.runInNewContext(source, { URL, document: { querySelector: () => page,
    getElementById: id => els[id] }, window: { setInterval() {} },
    navigator: { clipboard: { async writeText(value) { copied = value; } } } });
  return { els, page, copied: () => copied };
}

test('Felicitación sin teléfono permite copiar el mensaje completo', async () => {
  const { els, page, copied } = setup();
  const text = 'Estimado/a Ana María,\n\nMensaje\n\nAtentamente,\n\nJefatura de Enfermería';
  page.click({ target: { closest: () => ({ dataset: { name: 'Ana María', message: JSON.stringify(text), whatsappUrl: '' } }) } });
  assert.equal(els['birthday-dialog'].opened, true);
  assert.equal(els['birthday-send']['aria-disabled'], 'true');
  assert.equal(els['birthday-no-phone'].hidden, false);
  await els['birthday-copy'].click();
  assert.equal(copied(), text);
});

test('WhatsApp usa el mensaje editado de la persona seleccionada', () => {
  const { els, page } = setup();
  page.click({ target: { closest: () => ({ dataset: { name: 'Juan', message: JSON.stringify('Original'), whatsappUrl: 'https://wa.me/595981234567?text=Original' } }) } });
  els['birthday-message'].value = 'Mensaje editado';
  els['birthday-message'].input();
  assert.equal(new URL(els['birthday-send'].href).searchParams.get('text'), 'Mensaje editado');
  assert.equal(els['birthday-send']['aria-disabled'], 'false');
});

test('Cada tarjeta carga su propio mensaje y permite cerrar la ventana', () => {
  const { els, page } = setup();
  for (const name of ['Ana', 'Luis']) {
    page.click({ target: { closest: () => ({ dataset: { name, message: JSON.stringify(`Hola ${name}`), whatsappUrl: '' } }) } });
    assert.equal(els['birthday-message'].value, `Hola ${name}`);
    assert.equal(els['birthday-dialog-name'].textContent, name);
  }
  els['birthday-close'].click();
  assert.equal(els['birthday-dialog'].opened, false);
});
