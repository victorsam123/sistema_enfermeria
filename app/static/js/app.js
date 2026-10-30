const toggle = document.getElementById('toggle-password');
toggle?.addEventListener('click', () => {
  const field = document.getElementById('password');
  const visible = field.type === 'password';
  field.type = visible ? 'text' : 'password';
  toggle.setAttribute('aria-label', visible ? 'Ocultar contraseña' : 'Mostrar contraseña');
  toggle.setAttribute('aria-pressed', String(visible));
  toggle.firstElementChild.className = visible ? 'bi bi-eye-slash' : 'bi bi-eye';
});
document.getElementById('menu-toggle')?.addEventListener('click', (event) => {
  const expanded = document.getElementById('sidebar').classList.toggle('is-open');
  event.currentTarget.setAttribute('aria-expanded', String(expanded));
});

const dashboardClock = document.getElementById('dashboard-clock');
if (dashboardClock) {
  const dateOutput = document.getElementById('dashboard-date');
  const timeOutput = document.getElementById('dashboard-time');
  let epochMs = Number(dashboardClock.dataset.epochMs);
  let offsetSeconds = Number(dashboardClock.dataset.offsetSeconds);
  let anchor = performance.now();
  let syncing = false;
  const pad = (value) => String(value).padStart(2, '0');

  function renderClock() {
    // El desplazamiento proviene de zoneinfo en el servidor. Los getters UTC
    // evitan usar tanto la zona como las reglas horarias del dispositivo.
    const local = new Date(epochMs + performance.now() - anchor + offsetSeconds * 1000);
    const day = pad(local.getUTCDate());
    const month = pad(local.getUTCMonth() + 1);
    const year = local.getUTCFullYear();
    const time = `${pad(local.getUTCHours())}:${pad(local.getUTCMinutes())}:${pad(local.getUTCSeconds())}`;
    const isoDate = `${year}-${month}-${day}`;
    const offset = Math.abs(offsetSeconds);
    const isoOffset = `${offsetSeconds < 0 ? '-' : '+'}${pad(Math.floor(offset / 3600))}:${pad(Math.floor(offset % 3600 / 60))}`;
    dateOutput.textContent = `${day}/${month}/${year}`;
    dateOutput.dateTime = isoDate;
    timeOutput.textContent = time;
    timeOutput.dateTime = `${isoDate}T${time}${isoOffset}`;
  }

  async function syncClock() {
    if (syncing || document.hidden) return;
    syncing = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);
    const started = performance.now();
    try {
      const response = await fetch(dashboardClock.dataset.syncUrl, {
        cache: 'no-store', credentials: 'same-origin', signal: controller.signal,
        headers: { Accept: 'application/json' },
      });
      if (!response.ok || response.redirected) return;
      const snapshot = await response.json();
      if (snapshot.timezone !== 'America/Asuncion' || !Number.isFinite(snapshot.epoch_ms)
          || !Number.isFinite(snapshot.utc_offset_seconds)) return;
      const received = performance.now();
      epochMs = snapshot.epoch_ms + (received - started) / 2;
      offsetSeconds = snapshot.utc_offset_seconds;
      anchor = received;
      renderClock();
    } catch {
      // Una interrupción temporal conserva el avance desde la última muestra.
    } finally {
      clearTimeout(timeout);
      syncing = false;
    }
  }

  renderClock();
  setInterval(renderClock, 1000);
  setInterval(syncClock, 60000);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) syncClock();
  });
  window.addEventListener('pageshow', syncClock);
  syncClock();
}

const moduleDialog = document.getElementById('module-dialog');
if (moduleDialog) {
  document.querySelectorAll('[data-module]').forEach((button) => {
    button.addEventListener('click', () => {
      document.getElementById('module-dialog-title').textContent = button.dataset.moduleLabel;
      moduleDialog.showModal();
    });
  });
}
