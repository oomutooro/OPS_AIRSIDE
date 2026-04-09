(async function () {
  const chartCanvas = document.getElementById('incidentTrendChart');
  if (chartCanvas) {
    try {
      const resp = await fetch('/api/incident-trend');
      const data = await resp.json();
      new Chart(chartCanvas, {
        type: 'line',
        data: {
          labels: data.labels || [],
          datasets: [{
            label: 'Incidents',
            data: data.values || [],
            borderColor: '#1a56db',
            backgroundColor: 'rgba(26,86,219,0.15)',
            tension: 0.3,
            fill: true,
          }],
        },
        options: { plugins: { legend: { display: true } } }
      });
    } catch (e) {
      console.error('Could not load incident trend', e);
    }
  }

  const mapEl = document.getElementById('airsideMap');
  if (mapEl && window.L) {
    const map = L.map('airsideMap').setView([0.0424, 32.4435], 14);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors'
    }).addTo(map);

    L.marker([0.0424, 32.4435]).addTo(map).bindPopup('Entebbe International Airport');
  }
})();
