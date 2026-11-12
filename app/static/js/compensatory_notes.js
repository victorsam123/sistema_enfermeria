(() => {
  const form = document.querySelector('[data-compensatory-selection]');
  if (!form) return;
  const all = form.querySelector('[data-select-all]');
  const rows = [...form.querySelectorAll('[name="registros"]')];
  const count = form.querySelector('[data-selection-count]');
  function update() {
    const selected = rows.filter(row => row.checked).length;
    count.textContent = `${selected} seleccionado${selected === 1 ? '' : 's'}`;
    all.checked = rows.length > 0 && selected === rows.length;
    all.indeterminate = selected > 0 && selected < rows.length;
  }
  all.addEventListener('change', () => { rows.forEach(row => { row.checked = all.checked; }); update(); });
  rows.forEach(row => row.addEventListener('change', update));
  update();
})();
