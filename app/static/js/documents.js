'use strict';
function documentFileError(files, maximum, count) {
  if (files.length > count) return `Se permiten hasta ${count} fotografías por registro.`;
  for (const file of files) {
    if (!/\.(jpe?g|png|webp)$/i.test(file.name)) return 'Solo se admiten JPG, JPEG, PNG y WEBP. Convierte HEIC antes de cargarlo.';
    if (!file.size || file.size > maximum) return `Cada fotografía debe pesar hasta ${maximum / 1048576} MB y contener datos.`;
  }
  return '';
}
if (typeof module !== 'undefined') module.exports = { documentFileError };
if (typeof document !== 'undefined') {
  document.querySelectorAll('[data-document-upload]').forEach(zone => {
    const input = zone.querySelector('.document-file'), camera = zone.querySelector('.document-camera');
    const error = zone.querySelector('[data-upload-error]'), previews = zone.querySelector('[data-upload-previews]');
    const counter = zone.querySelector('[data-upload-count]'), maximum = Number(zone.dataset.maxBytes), count = Number(zone.dataset.maxFiles);
    if (typeof DataTransfer === 'undefined') return;
    let selected = [], urls = [];
    zone.classList.add('enhanced');
    if (window.matchMedia('(pointer: coarse)').matches && 'capture' in camera) zone.querySelector('.document-camera-button').hidden = false;
    const sync = () => { const transfer = new DataTransfer(); selected.forEach(file => transfer.items.add(file)); input.files = transfer.files; };
    const render = () => {
      urls.forEach(url => URL.revokeObjectURL(url)); urls = []; previews.replaceChildren();
      selected.forEach((file, index) => {
        const card = document.createElement('article'), img = document.createElement('img'), label = document.createElement('p'), remove = document.createElement('button');
        card.className = 'document-preview'; img.src = URL.createObjectURL(file); urls.push(img.src); img.alt = `Vista previa de fotografía ${index + 1}`;
        label.textContent = `${file.name} · ${(file.size / 1048576).toFixed(2)} MB`;
        remove.type = 'button'; remove.className = 'btn admin-secondary'; remove.textContent = 'Quitar fotografía';
        remove.addEventListener('click', () => { selected.splice(index, 1); error.textContent = ''; sync(); render(); });
        card.append(img, label, remove); previews.append(card);
      });
      counter.textContent = selected.length ? `${selected.length} fotografía(s) seleccionada(s).` : 'Sin fotografías seleccionadas.';
    };
    const add = files => {
      const next = [...selected];
      Array.from(files).forEach(file => { if (!next.some(p => p.name === file.name && p.size === file.size && p.lastModified === file.lastModified)) next.push(file); });
      const message = documentFileError(next, maximum, count); error.textContent = message;
      if (!message) selected = next;
      sync(); render();
    };
    input.addEventListener('change', () => add(input.files));
    camera.addEventListener('change', () => { add(camera.files); camera.value = ''; });
    zone.closest('form').addEventListener('submit', event => {
      const message = documentFileError(Array.from(input.files), maximum, count);
      if (message) { event.preventDefault(); event.stopImmediatePropagation(); error.textContent = message; }
    }, true);
    window.addEventListener('pagehide', () => urls.forEach(url => URL.revokeObjectURL(url)));
  });
  const viewer = document.querySelector('[data-document-viewer]');
  if (viewer) {
    const buttons = Array.from(document.querySelectorAll('[data-gallery-open]'));
    const image = viewer.querySelector('[data-viewer-image]'), stage = viewer.querySelector('.viewer-stage');
    let index = 0, zoom = 1, opener;
    const drawZoom = () => { stage.className = `viewer-stage zoom-${zoom}`; viewer.querySelector('[data-zoom-label]').textContent = `${[100,175,250][zoom - 1]}%`; };
    const show = position => { index = (position + buttons.length) % buttons.length; image.src = buttons[index].dataset.imageUrl; image.alt = buttons[index].dataset.imageLabel;
      viewer.querySelector('[data-viewer-label]').textContent = `${index + 1} / ${buttons.length} · ${image.alt}`; zoom = 1; drawZoom(); stage.scrollTo(0, 0); };
    buttons.forEach((button, i) => button.addEventListener('click', () => { opener = button; show(i); viewer.showModal(); }));
    viewer.querySelector('[data-viewer-close]').addEventListener('click', () => viewer.close());
    viewer.addEventListener('close', () => { image.removeAttribute('src'); opener?.focus(); });
    viewer.querySelector('[data-viewer-prev]').addEventListener('click', () => show(index - 1));
    viewer.querySelector('[data-viewer-next]').addEventListener('click', () => show(index + 1));
    viewer.querySelector('[data-zoom-in]').addEventListener('click', () => { zoom = Math.min(3, zoom + 1); drawZoom(); });
    viewer.querySelector('[data-zoom-out]').addEventListener('click', () => { zoom = Math.max(1, zoom - 1); drawZoom(); });
    viewer.addEventListener('keydown', event => { if (event.key === 'ArrowLeft') show(index - 1); if (event.key === 'ArrowRight') show(index + 1); });
  }
}
