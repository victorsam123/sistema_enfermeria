(() => {
  const form = document.getElementById('guardia-form');
  if (!form || form.dataset.category === 'NORMAL') return;

  const rows = [...form.querySelectorAll('[data-guardia-index]')];
  if (form.dataset.category === 'REEMPLAZO' && rows.length === 4) {
    for (const [source, target] of [[rows[0], rows[1]], [rows[2], rows[3]]]) {
      for (const suffix of ['fecha_guardia', 'hora_inicio', 'hora_fin']) {
        const from = source.querySelector(`[name$="-${suffix}"]`);
        const to = target.querySelector(`[name$="-${suffix}"]`);
        to.readOnly = true;
        const copy = () => {
          to.value = from.value;
          to.dispatchEvent(new Event('input', { bubbles: true }));
        };
        from.addEventListener('input', copy);
        copy();
      }
      const picker = target.querySelector('[data-date-for]');
      if (picker) picker.disabled = true;
    }
    for (const row of rows) {
      const code = row.querySelector('[data-code]');
      for (const option of [...code.options]) if (option.value !== code.value) option.remove();
    }
  }

  const category = form.dataset.category;
  const labels = {REEMPLAZO: 'con reemplazante', PAGADA: 'pagados', EMERGENCIA: 'de emergencia'};
  const quotaRoles = category === 'REEMPLAZO' ? ['solicitante', 'reemplazante'] : ['solicitante'];
  const panels = Object.fromEntries(['solicitante', 'reemplazante'].map(role => [
    role, form.querySelector(`[data-monthly-role="${role}"]`),
  ]));
  if (category !== 'REEMPLAZO' && panels.reemplazante) panels.reemplazante.hidden = true;

  let timer;
  let revision = 0;
  let submittingAfterConfirmation = false;

  function quotaDate() {
    const raw = form.dataset.quotaDate || form.querySelector('[name$="-fecha_guardia"]').value;
    const match = raw.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
    return match ? new Date(Number(match[3]), Number(match[2]) - 1, Number(match[1])) : null;
  }

  function quotaPayload(role) {
    const nameField = form.elements.namedItem(role);
    return {
      nombre: nameField.value,
      funcionario_id: form.elements.namedItem(`${role}_funcionario_id`).value,
      fecha: form.dataset.quotaDate || form.querySelector('[name$="-fecha_guardia"]').value,
      tipo_cambio: category,
      record_id: form.dataset.recordId || null,
      ticket: form.querySelector('[data-employee-lookup]').dataset.context,
    };
  }

  async function getQuota(role) {
    const response = await fetch(form.dataset.monthlyUrl, {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': form.elements.namedItem('csrf_token').value},
      body: JSON.stringify(quotaPayload(role)),
    });
    if (!response.ok) throw new Error(`No se pudo consultar el cupo (HTTP ${response.status}).`);
    return response.json();
  }

  function quotaText(name, data) {
    const kind = category;
    return `${name}: ${data.mes}. Cupo mensual: ${data.limites[kind]}. Cambios utilizados: ${data.usados[kind]}. Disponibles: ${data.disponibles[kind]}. `
      + `${data.mes_siguiente}. Cambios anticipados: ${data.anticipados[kind]}. `
      + `Disponibles del mes siguiente: ${data.disponibles_mes_siguiente[kind]}.`;
  }

  async function refresh() {
    const currentRevision = ++revision;
    await Promise.all(['solicitante', 'reemplazante'].map(async role => {
      const panel = panels[role];
      if (!panel) return;
      const nameField = form.elements.namedItem(role);
      const name = nameField.value.trim();
      const id = form.elements.namedItem(`${role}_funcionario_id`).value;
      if (!name && !id) {
        panel.textContent = `Selecciona el ${role} para consultar sus cupos.`;
        return;
      }
      panel.textContent = `${name}: consultando control mensual…`;
      try {
        const data = await getQuota(role);
        if (currentRevision !== revision) return;
        const applies = quotaRoles.includes(role);
        nameField.setCustomValidity(!form.dataset.editing && applies && !data.puede_guardar
          ? `${name} no tiene cupos disponibles para esta fecha.` : '');
        panel.textContent = quotaText(name, data);
        if (applies && !data.puede_guardar) panel.textContent += ' No hay cupos disponibles para este cambio.';
      } catch (error) {
        if (currentRevision === revision) {
          nameField.setCustomValidity('');
          panel.textContent = 'No se pudo consultar el cupo. Revisa la conexión; el servidor verificará el límite al guardar.';
          console.error(error);
        }
      }
    }));
  }

  function schedule() {
    clearTimeout(timer);
    ++revision;
    for (const role of quotaRoles) form.elements.namedItem(role).setCustomValidity('');
    timer = setTimeout(refresh, 300);
  }

  const dialog = form.querySelector('#guardia-quota-confirmation');
  const confirmationMessage = form.querySelector('#guardia-quota-confirmation-message');
  const confirmationField = form.querySelector('#confirmar-cupo-anticipado');

  async function confirmRequiredAdvance() {
    const date = quotaDate();
    if (!date) return false;
    const results = await Promise.all(quotaRoles.map(async role => {
      const data = await getQuota(role);
      const name = form.elements.namedItem(role).value.trim();
      if (!data.puede_guardar) {
        form.elements.namedItem(role).setCustomValidity(`${name} no tiene cupos disponibles para esta fecha.`);
        return {blocked: true};
      }
      if (data.requiere_anticipacion) {
        return {advanced: true, name, month: data.mes_siguiente};
      }
      return {};
    }));
    if (results.some(result => result.blocked)) {
      form.reportValidity();
      return false;
    }
    const advances = results.filter(result => result.advanced);
    if (!advances.length) return true;

    const names = [...new Set(advances.map(result => result.name))].join(', ');
    const months = [...new Set(advances.map(result => result.month))].join(', ');
    confirmationMessage.textContent = `${names} ha agotado sus cupos del mes actual. Este cambio será descontado del cupo de ${months}.`;
    dialog.showModal();
    return false;
  }

  form.addEventListener('input', schedule);
  form.addEventListener('change', schedule);
  form.querySelectorAll('[data-lookup-clear]').forEach(button => button.addEventListener('click', schedule));
  form.addEventListener('submit', async event => {
    if (submittingAfterConfirmation || form.dataset.category === 'NORMAL') return;
    event.preventDefault();
    try {
      const ready = await confirmRequiredAdvance();
      if (ready) {
        submittingAfterConfirmation = true;
        form.requestSubmit(event.submitter);
      }
    } catch (error) {
      console.error('No se pudo verificar el cupo antes de guardar:', error);
      form.reportValidity();
    }
  });

  form.querySelector('#guardia-quota-confirm')?.addEventListener('click', () => {
    confirmationField.value = '1';
    submittingAfterConfirmation = true;
    dialog.close();
    form.requestSubmit();
  });
  form.querySelector('#guardia-quota-cancel')?.addEventListener('click', () => dialog.close());

  const serverMessage = form.dataset.advanceConfirmationMessage;
  if (serverMessage) {
    confirmationMessage.textContent = serverMessage;
    dialog.showModal();
  }
  refresh();
})();
