(function () {
  document.querySelectorAll('[data-action]').forEach(function (el) {
    el.addEventListener('click', function (e) {
      var action = e.currentTarget.dataset.action;
      if (action === 'analyzeTicker') {
        htmx.ajax('GET', '/analyze', { target: 'body', swap: 'innerHTML' });
        setTimeout(function () {
          var input = document.querySelector('#analyze-form input[name="ticker"]');
          if (input) input.value = e.currentTarget.dataset.ticker;
        }, 100);
      }
    });
  });
})();
