const test = require('node:test');
const assert = require('node:assert/strict');
const { documentFileError } = require('../app/static/js/documents.js');
const max = 8 * 1024 * 1024;
test('Fotografías opcionales y extensiones de móviles', () => {
  assert.equal(documentFileError([], max, 5), '');
  for (const name of ['foto.jpg','foto.JPEG','foto.png','foto.WEBP']) assert.equal(documentFileError([{name,size:max}],max,5),'');
});
test('Rechaza tamaños y cantidades excesivos', () => {
  assert.match(documentFileError([{name:'a.png',size:max+1}],max,5), /MB/);
  assert.match(documentFileError([{name:'a.png',size:0}],max,5), /datos/);
  assert.match(documentFileError(Array(6).fill({name:'a.png',size:1}),max,5), /hasta 5/);
});
test('No permite HEIC, SVG ni ejecutables en el selector', () => {
  for (const name of ['a.heic','a.svg','foto.jpg.exe','sinextension']) assert.match(documentFileError([{name,size:100}],max,5), /Solo se admiten/);
});
