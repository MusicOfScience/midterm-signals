const election = new Date('2026-11-03T20:00:00-05:00');
const daysEl = document.querySelector('#days');
function updateCountdown(){
  const ms = election - new Date();
  daysEl.textContent = ms <= 0 ? '0' : Math.ceil(ms / 86400000).toString();
}
updateCountdown();

const nav = document.querySelector('#nav');
const menu = document.querySelector('.menu');
menu?.addEventListener('click', () => {
  const open = nav.classList.toggle('open');
  menu.setAttribute('aria-expanded', String(open));
});

function show(view){
  document.querySelectorAll('[data-panel]').forEach(el => el.classList.toggle('hidden', el.dataset.panel !== view));
  document.querySelectorAll('.nav-link').forEach(el => el.classList.toggle('active', el.dataset.view === view));
  nav.classList.remove('open');
  menu?.setAttribute('aria-expanded','false');
  window.scrollTo({top:0,behavior:'smooth'});
}

document.addEventListener('click', (event) => {
  const target = event.target.closest('[data-view]');
  if (!target) return;
  event.preventDefault();
  show(target.dataset.view);
});
