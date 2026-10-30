/* El servidor verifica nuevamente el servicio y PostgreSQL impone la FK. */
(() => {
  const dialog = document.getElementById('service-dialog');
  if (!dialog || typeof dialog.showModal !== 'function') return;
  const choice = document.getElementById('service-confirm-choice');
  let pendingForm = null;
  let pendingButton = null;
  document.querySelectorAll('.administrative-form').forEach((form) => {
    const selector = form.querySelector('[data-service-selector]');
    if (!selector) return;
    form.addEventListener('submit', (event) => {
      if (Number(selector.value) > 0) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      pendingForm = form;
      pendingButton = event.submitter;
      choice.replaceChildren();
      for (const option of selector.options) {
        const copy = option.cloneNode(true);
        if (copy.value === '0') copy.value = '';
        choice.appendChild(copy);
      }
      choice.value = '';
      dialog.showModal();
      choice.focus();
    }, true);
  });
  document.getElementById('service-confirmation').addEventListener('submit', (event) => {
    event.preventDefault();
    if (!choice.value || !pendingForm) return;
    const form = pendingForm;
    form.querySelector('[data-service-selector]').value = choice.value;
    dialog.close();
    form.requestSubmit(pendingButton || undefined);
  });
  document.getElementById('service-cancel').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => { pendingForm = null; pendingButton = null; });
})();
