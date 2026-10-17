document.addEventListener('DOMContentLoaded', () => {
  const demoAccounts = {
    admin: { username: 'admin', password: 'admin123' },
    manager: { username: 'manager', password: 'manager123' },
    user: { username: 'user', password: 'user123' },
  };
  const roles = document.getElementById('rtk-demo-roles');
  const hint = document.getElementById('rtk-demo-hint');
  const username = document.getElementById('username');
  const password = document.getElementById('password');
  if (!roles || !username || !password) return;

  let filling = false;
  const clearDemoSelection = () => {
    if (filling) return;
    const selected = roles.querySelector('[data-demo-role]:checked');
    if (selected) selected.checked = false;
    if (hint) hint.hidden = true;
  };
  username.addEventListener('input', clearDemoSelection);
  password.addEventListener('input', clearDemoSelection);

  roles.querySelectorAll('[data-demo-role]').forEach((radio) => {
    radio.addEventListener('change', () => {
      if (!radio.checked) return;
      const account = demoAccounts[radio.dataset.demoRole];
      if (!account) return;
      filling = true;
      username.value = account.username;
      password.value = account.password;
      username.dispatchEvent(new Event('input', { bubbles: true }));
      password.dispatchEvent(new Event('input', { bubbles: true }));
      filling = false;
      if (hint) hint.hidden = false;
      document.getElementById('kc-login')?.focus();
    });
  });
});
