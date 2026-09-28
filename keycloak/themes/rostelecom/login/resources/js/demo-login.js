document.addEventListener('DOMContentLoaded', () => {
  const demoAccounts = {
    admin: { username: 'admin', password: 'admin123' },
    manager: { username: 'manager', password: 'manager123' },
    user: { username: 'user', password: 'user123' },
  };
  const toggle = document.getElementById('rtk-demo-toggle');
  const roles = document.getElementById('rtk-demo-roles');
  if (!toggle || !roles) return;

  toggle.addEventListener('click', () => {
    roles.hidden = !roles.hidden;
    toggle.setAttribute('aria-expanded', String(!roles.hidden));
  });
  roles.querySelectorAll('[data-demo-role]').forEach((button) => {
    button.addEventListener('click', () => {
      const account = demoAccounts[button.dataset.demoRole];
      const username = document.getElementById('username');
      const password = document.getElementById('password');
      if (!account || !username || !password) return;
      username.value = account.username;
      password.value = account.password;
      username.dispatchEvent(new Event('input', { bubbles: true }));
      password.dispatchEvent(new Event('input', { bubbles: true }));
      roles.hidden = true;
      toggle.setAttribute('aria-expanded', 'false');
      document.getElementById('kc-login')?.focus();
    });
  });
});
