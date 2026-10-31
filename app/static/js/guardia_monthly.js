(() => {
  const form = document.getElementById('guardia-form');
  if (!form || form.dataset.category === 'NORMAL') return;
  const rows = [...form.querySelectorAll('[data-guardia-index]')];
  if (form.dataset.category === 'REEMPLAZO' && rows.length === 4) {
    // Se carga una sola vez el horario de cada guardia; se refleja en quien cubre.
    for (const [source, target] of [[rows[0], rows[1]], [rows[2], rows[3]]]) {
      for (const suffix of ['fecha_guardia', 'hora_inicio', 'hora_fin']) {
        const from = source.querySelector(`[name$="-${suffix}"]`);
        const to = target.querySelector(`[name$="-${suffix}"]`);
        to.readOnly = true;
        const copy = () => { to.value = from.value; to.dispatchEvent(new Event('input', { bubbles: true })); };
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
  let timer, revision = 0;
  const labels = {REEMPLAZO: 'con reemplazante', PAGADA: 'pagados', EMERGENCIA: 'de emergencia'};
  async function refresh() {
    const current = ++revision;
    const date = form.dataset.quotaDate || form.querySelector('[name$="-fecha_guardia"]').value;
    await Promise.all(['solicitante', 'reemplazante'].map(async role => {
      const panel = form.querySelector(`[data-monthly-role="${role}"]`);
      if (!panel) return;
      const name = form.elements.namedItem(role).value;
      const nameField = form.elements.namedItem(role);
      const id = form.elements.namedItem(`${role}_funcionario_id`).value;
      if (!name.trim() && !id) { panel.textContent = `Selecciona el ${role} para consultar sus cupos.`; return; }
      panel.textContent = `${name}: consultando control mensual…`;
      try {
        const response = await fetch(form.dataset.monthlyUrl, {method: 'POST',
          headers: {'Content-Type': 'application/json', 'X-CSRFToken': form.elements.namedItem('csrf_token').value},
          body: JSON.stringify({nombre: name, funcionario_id: id, fecha: date,
            ticket: form.querySelector('[data-employee-lookup]').dataset.context})});
        if (!response.ok) throw new Error();
        const data = await response.json();
        if (current !== revision) return;
        const kind = form.dataset.category;
        const applies = role === 'solicitante' || kind === 'REEMPLAZO';
        nameField.setCustomValidity(!form.dataset.editing && applies && !data.disponibles[kind]
          ? `${name} ya alcanzó el límite mensual de cambios ${labels[kind]} (${data.usados[kind]} de ${data.limites[kind]}).` : '');
        panel.replaceChildren();
        const title = document.createElement('strong');
        title.textContent = `${name} · ${data.mes}`;
        panel.append(title);
        for (const kind of Object.keys(labels)) {
          const line = document.createElement('p');
          line.textContent = `Cambios ${labels[kind]}: ${data.usados[kind]} de ${data.limites[kind]} realizados. ${data.disponibles[kind]} disponibles.`;
          if (!data.disponibles[kind]) line.textContent += ' Límite mensual alcanzado.';
          panel.append(line);
        }
      } catch {
        if (current === revision) panel.textContent = 'No se pudo consultar el cupo. Revisa la fecha y la conexión; el servidor verificará el límite al guardar.';
      }
    }));
  }
  const schedule = () => {
    clearTimeout(timer); ++revision;
    for (const role of ['solicitante', 'reemplazante']) form.elements.namedItem(role).setCustomValidity('');
    timer = setTimeout(refresh, 300);
  };
  form.addEventListener('input', schedule);
  form.addEventListener('change', schedule);
  form.querySelectorAll('[data-lookup-clear]').forEach(button => button.addEventListener('click', schedule));
  refresh();
})();
