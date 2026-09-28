const toggle = document.getElementById('rtk-demo-toggle');
const roles = document.getElementById('rtk-demo-roles');
if (toggle && roles) {
  toggle.addEventListener('click', () => {
    roles.hidden = !roles.hidden;
    toggle.setAttribute('aria-expanded', String(!roles.hidden));
  });
  roles.querySelectorAll('[data-demo-role]').forEach((button) => {
    button.addEventListener('click', () => {
      const username = document.getElementById('username');
      const password = document.getElementById('password');
      if (username) username.value = button.dataset.demoRole;
      roles.hidden = true;
      toggle.setAttribute('aria-expanded', 'false');
      password?.focus();
    });
  });
}
