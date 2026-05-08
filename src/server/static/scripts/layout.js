function syncTab() {
  var path = window.location.pathname;
  document.querySelectorAll('.tab').forEach(function(tab) {
    tab.classList.toggle('active', tab.getAttribute('hx-get') === path);
  });
}
syncTab();
document.body.addEventListener('htmx:afterSwap', syncTab);
