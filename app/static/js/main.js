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

    // Auto-init DataTables only for tables that are safe for enhancement.
    $('.table').each(function () {
      const $table = $(this);

      if ($table.hasClass('no-datatable')) {
        return;
      }

      if ($.fn.dataTable.isDataTable(this)) {
        return;
      }

      // DataTables requires consistent column structure; skip colspan-based empty rows.
      if ($table.find('tbody td[colspan], tbody th[colspan]').length > 0) {
        return;
      }

      const orderAttr = $table.attr('data-order');
      const orderOpt = orderAttr ? JSON.parse(orderAttr) : [[0, 'asc']];
      $table.DataTable({ responsive: true, pageLength: 10, order: orderOpt });
    });
  }

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/static/js/pwa_sw.js').catch(function (err) {
      console.warn('Service worker registration failed', err);
    });
  }
})();
