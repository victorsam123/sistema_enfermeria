document.querySelectorAll('[data-password-toggle]').forEach((button) => {
  button.addEventListener('click', () => {
    const field = document.getElementById(button.dataset.passwordToggle);
    const visible = field.type === 'password';
    field.type = visible ? 'text' : 'password';
    button.setAttribute('aria-label', visible ? 'Ocultar contraseña' : 'Mostrar contraseña');
    button.setAttribute('aria-pressed', String(visible));
    button.querySelector('i').className = visible ? 'bi bi-eye-slash' : 'bi bi-eye';
  });
});
