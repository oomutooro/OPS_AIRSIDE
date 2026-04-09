(function () {
  document.querySelectorAll('form').forEach(function (form) {
    form.addEventListener('submit', function (event) {
      if (!form.checkValidity()) {
        event.preventDefault();
        event.stopPropagation();
      }
      form.classList.add('was-validated');
    });
  });

  document.querySelectorAll('[data-conditional-target]').forEach(function (el) {
    el.addEventListener('change', function () {
      const targetId = el.getAttribute('data-conditional-target');
      const showOn = el.getAttribute('data-show-on') || 'BAD';
      const target = document.getElementById(targetId);
      if (!target) return;
      if (el.value === showOn) target.classList.add('active');
      else target.classList.remove('active');
    });
  });
})();
