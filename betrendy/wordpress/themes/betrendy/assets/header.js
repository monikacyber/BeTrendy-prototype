/* Native details/search stays usable without JavaScript. */
(() => {
  'use strict';
  const search = document.querySelector('.bt-compact-search');
  if (!search) return;
  const summary = search.querySelector('summary');
  const close = (restoreFocus = false) => {
    search.open = false;
    if (restoreFocus) summary.focus();
  };
  search.addEventListener('toggle', () => {
    if (search.open) search.querySelector('input[type="search"]')?.focus();
  });
  document.addEventListener('click', (event) => {
    if (search.open && !search.contains(event.target)) close();
  });
  search.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') { event.preventDefault(); close(true); }
  });
  search.addEventListener('focusout', () => {
    window.setTimeout(() => {
      if (search.open && !search.contains(document.activeElement)) close();
    }, 0);
  });
})();
