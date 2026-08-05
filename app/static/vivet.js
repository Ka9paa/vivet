document.addEventListener('click', (event) => {
  const opener = event.target.closest('[data-open]');
  if (opener) document.getElementById(opener.dataset.open)?.showModal();
  const closer = event.target.closest('[data-close]');
  if (closer) closer.closest('dialog')?.close();
});
const menu = document.getElementById('menu-toggle');
const sidebar = document.getElementById('sidebar');
const overlay = document.getElementById('sidebar-overlay');
const closeMenu = () => { sidebar?.classList.remove('open'); overlay?.classList.remove('show'); };
menu?.addEventListener('click', () => { sidebar?.classList.toggle('open'); overlay?.classList.toggle('show'); });
overlay?.addEventListener('click', closeMenu);
document.querySelectorAll('.side-nav a').forEach(link => link.addEventListener('click', closeMenu));


const searchInput = document.getElementById('nav-search');
searchInput?.addEventListener('input', () => {
  const q = searchInput.value.toLowerCase().trim();
  document.querySelectorAll('.side-nav a').forEach((link) => {
    link.style.display = link.textContent.toLowerCase().includes(q) ? '' : 'none';
  });
});

document.querySelectorAll('button.primary, a.primary, .quick-action').forEach((el) => {
  el.addEventListener('pointerdown', () => el.classList.add('pressed'));
  ['pointerup','pointerleave'].forEach(evt => el.addEventListener(evt, () => el.classList.remove('pressed')));
});

window.addEventListener('load', () => {
  document.body.classList.add('loaded');
});


document.querySelectorAll('[data-password-toggle]').forEach((button) => {
  button.addEventListener('click', () => {
    const input = document.getElementById(button.dataset.passwordToggle);
    if (!input) return;
    const showing = input.type === 'text';
    input.type = showing ? 'password' : 'text';
    button.textContent = showing ? 'Show' : 'Hide';
    button.setAttribute('aria-label', showing ? 'Show password' : 'Hide password');
  });
});




// Unified Vivet modal interactions.
let pendingConfirmedForm = null;
const confirmationDialog = document.getElementById('confirm-action');
const confirmationMessage = document.getElementById('confirm-message');

document.querySelectorAll('dialog.modal').forEach((dialog) => {
  dialog.addEventListener('click', (event) => {
    if (event.target === dialog) dialog.close();
  });
  dialog.addEventListener('close', () => {
    const submit = dialog.querySelector('.modal-submit');
    submit?.classList.remove('is-loading');
    const text = submit?.querySelector('span');
    if (text && submit.dataset.originalText) text.textContent = submit.dataset.originalText;
  });
});

document.addEventListener('submit', (event) => {
  const form = event.target;
  const message = form.dataset.confirm;
  if (message && !form.dataset.confirmed) {
    event.preventDefault();
    pendingConfirmedForm = form;
    if (confirmationMessage) confirmationMessage.textContent = message;
    confirmationDialog?.showModal();
    return;
  }
  const submit = form.querySelector('.modal-submit');
  if (!submit) return;
  submit.classList.add('is-loading');
  const text = submit.querySelector('span');
  if (text) {
    submit.dataset.originalText = text.textContent;
    text.textContent = 'Working';
  }
});

document.getElementById('confirm-submit')?.addEventListener('click', (event) => {
  event.preventDefault();
  if (!pendingConfirmedForm) return confirmationDialog?.close();
  pendingConfirmedForm.dataset.confirmed = 'true';
  confirmationDialog?.close();
  pendingConfirmedForm.requestSubmit();
  pendingConfirmedForm = null;
});
