(() => {
  const page = document.querySelector('#novedades-page');
  if (!page) return;

  const dialog = document.getElementById('birthday-dialog');
  const message = document.getElementById('birthday-message');
  const send = document.getElementById('birthday-send');
  const noPhone = document.getElementById('birthday-no-phone');
  const status = document.getElementById('birthday-copy-status');
  let whatsappUrl = '';
  let initialMessage = '';
  let employeeName = '';
  const updateLink = () => {
    if (!whatsappUrl) return;
    const url = new URL(whatsappUrl);
    let text = message.value;
    if (text === initialMessage) {
      text = text.replace(`Estimado/a ${employeeName},`, `Estimado/a *${employeeName}*,`);
      text = text.replace(/Jefatura de Enfermería$/, '*Jefatura de Enfermería*');
    }
    url.searchParams.set('text', text);
    send.href = url.toString();
  };
  page.addEventListener('click', (event) => {
    const button = event.target.closest('.birthday-greeting');
    if (!button) return;
    employeeName = button.dataset.name;
    initialMessage = JSON.parse(button.dataset.message);
    message.value = initialMessage;
    document.getElementById('birthday-dialog-name').textContent = employeeName;
    whatsappUrl = button.dataset.whatsappUrl;
    noPhone.hidden = Boolean(whatsappUrl);
    status.textContent = '';
    send.setAttribute('aria-disabled', String(!whatsappUrl));
    if (whatsappUrl) updateLink(); else send.removeAttribute('href');
    dialog.showModal();
  });
  message.addEventListener('input', updateLink);
  document.getElementById('birthday-copy').addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(message.value);
      status.textContent = 'Felicitación copiada.';
    } catch (_) {
      message.focus();
      message.select();
      status.textContent = 'Selecciona y copia el mensaje manualmente.';
    }
  });
  document.getElementById('birthday-close').addEventListener('click', () => dialog.close());

  const refreshUrl = page.dataset.refreshUrl;
  const refreshDelayMs = 60000;

  page.addEventListener('error', (event) => {
    const image = event.target;
    if (!(image instanceof HTMLImageElement) || !image.matches('.news-avatar img')) return;

    const fallback = document.createElement('span');
    fallback.className = 'news-avatar news-avatar-fallback';
    fallback.setAttribute('aria-hidden', 'true');
    fallback.innerHTML = '<i class="bi bi-person"></i>';
    image.parentElement.replaceWith(fallback);
  }, true);

  const refreshPage = async () => {
    try {
      const response = await fetch(refreshUrl, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        cache: 'no-store',
      });
      if (!response.ok) {
        throw new Error(`No se pudo actualizar Novedades (HTTP ${response.status}).`);
      }

      const snapshot = await response.json();
      const pageDate = document.querySelector('#dashboard-date')?.dateTime;
      if (snapshot.fecha_actual && pageDate !== snapshot.fecha_actual) {
        window.location.reload();
      }
    } catch (error) {
      console.error('Error al actualizar los avisos de Novedades:', error);
    }
  };

  window.setInterval(refreshPage, refreshDelayMs);
})();
