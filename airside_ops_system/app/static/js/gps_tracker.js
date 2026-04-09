(function () {
  function captureGPS(form) {
    if (!navigator.geolocation) {
      alert('Geolocation is not supported on this device.');
      return;
    }

    navigator.geolocation.getCurrentPosition(
      (position) => {
        const latInput = form.querySelector('.gps-lat');
        const lngInput = form.querySelector('.gps-lng');
        if (latInput) latInput.value = position.coords.latitude.toFixed(6);
        if (lngInput) lngInput.value = position.coords.longitude.toFixed(6);
      },
      (error) => {
        console.warn('GPS capture failed', error);
        alert('Unable to capture GPS location.');
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
    );
  }

  document.querySelectorAll('.btn-capture-gps').forEach((btn) => {
    btn.addEventListener('click', () => {
      const form = btn.closest('form');
      if (form) captureGPS(form);
    });
  });
})();
