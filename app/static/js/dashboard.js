(function () {
  const payloadNode = document.getElementById('dashboard-payload');
  if (!payloadNode) return;

  let payload = {};
  try {
    payload = JSON.parse(payloadNode.textContent || '{}');
  } catch (err) {
    console.error('Invalid dashboard payload JSON', err);
    return;
  }

  const arrDep = payload.arrDep || { labels: [], arrivals: [], departures: [] };
  const hourly = payload.hourly || { labels: [], values: [], peak_hour: '-', peak_volume: 0 };

  const arrDepCanvas = document.getElementById('arrDepChart');
  if (arrDepCanvas && window.Chart) {
    if (arrDepCanvas._chartInstance) {
      arrDepCanvas._chartInstance.destroy();
    }
    arrDepCanvas._chartInstance = new Chart(arrDepCanvas, {
      type: 'bar',
      data: {
        labels: arrDep.labels || [],
        datasets: [
          {
            label: 'Arrivals',
            data: arrDep.arrivals || [],
            backgroundColor: 'rgba(37, 99, 235, 0.8)',
            borderColor: 'rgba(30, 64, 175, 1)',
            borderWidth: 1,
          },
          {
            label: 'Departures',
            data: arrDep.departures || [],
            backgroundColor: 'rgba(217, 119, 6, 0.82)',
            borderColor: 'rgba(180, 83, 9, 1)',
            borderWidth: 1,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'bottom' },
        },
        scales: {
          y: { beginAtZero: true, ticks: { precision: 0 } },
        },
      },
    });
  }

  const peakCanvas = document.getElementById('peakChart');
  if (peakCanvas && window.Chart) {
    if (peakCanvas._chartInstance) {
      peakCanvas._chartInstance.destroy();
    }
    peakCanvas._chartInstance = new Chart(peakCanvas, {
      type: 'line',
      data: {
        labels: hourly.labels || [],
        datasets: [
          {
            label: 'Movements per Hour',
            data: hourly.values || [],
            borderColor: 'rgba(14, 165, 233, 1)',
            backgroundColor: 'rgba(14, 165, 233, 0.25)',
            fill: true,
            tension: 0.25,
            pointRadius: 2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'bottom' },
        },
        scales: {
          y: { beginAtZero: true, ticks: { precision: 0 } },
        },
      },
    });
  }

  const peakHourText = document.getElementById('peakHourText');
  const peakVolumeText = document.getElementById('peakVolumeText');
  if (peakHourText) peakHourText.textContent = hourly.peak_hour || '-';
  if (peakVolumeText) peakVolumeText.textContent = String(hourly.peak_volume || 0);
})();
