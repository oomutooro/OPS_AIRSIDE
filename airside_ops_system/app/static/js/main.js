(function () {
  const sidebarToggle = document.getElementById('sidebarToggle');
  const sidebar = document.getElementById('sidebar');

  if (sidebarToggle && sidebar) {
    sidebarToggle.addEventListener('click', function () {
      sidebar.classList.toggle('open');
    });
  }

  if (window.jQuery) {
    $('.datepicker').flatpickr({
      enableTime: false,
      dateFormat: 'Y-m-d'
    });

    $('.datetimepicker').flatpickr({
      enableTime: true,
      time_24hr: true,
      dateFormat: 'Y-m-d H:i'
    });

    $('select[multiple], .select2').select2({ width: '100%' });
    $('.table').DataTable({ responsive: true, pageLength: 10 });
  }

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/static/js/pwa_sw.js').catch(function (err) {
      console.warn('Service worker registration failed', err);
    });
  }
})();
