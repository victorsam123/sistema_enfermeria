(() => {
  const page = document.querySelector('#novedades-page');
  if (!page) return;

  const refreshUrl = page.dataset.refreshUrl;
  const refreshDelayMs = 60000;

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
