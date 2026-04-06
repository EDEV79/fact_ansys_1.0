/* ============================================================
  Fact Ansys 1.0 — Dashboard charts
   ============================================================ */

const PALETTE = [
  '#14213d',
  '#274c77',
  '#4d7c8a',
  '#7bdff2',
  '#f4a261',
  '#e76f51',
  '#ffd166',
  '#8ecae6',
  '#219ebc',
  '#fb8500',
  '#a8dadc',
  '#457b9d',
  '#1d3557',
  '#e63946',
  '#2a9d8f',
];

function currencyFmt(value) {
  return (
    '$' +
    Number(value).toLocaleString('es-PA', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })
  );
}

/* ── Legacy: emisorChart (dashboard DGI) ─────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  // Legacy bar chart for DGI dashboard
  const legacyEl = document.getElementById('emisorChart');
  const legacyPayload = document.getElementById('chart-data');
  if (legacyEl && legacyPayload) {
    const data = JSON.parse(legacyPayload.textContent);
    new Chart(legacyEl, {
      type: 'bar',
      data: {
        labels: data.labels,
        datasets: [
          {
            label: 'Monto total',
            data: data.values,
            borderRadius: 10,
            backgroundColor: PALETTE,
          },
        ],
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: {
          y: {
            beginAtZero: true,
            ticks: { callback: currencyFmt },
          },
        },
      },
    });
  }

  /* ── Monthly bar chart (client detail) ──────────────────── */
  const monthlyEl = document.getElementById('monthlyChart');
  const monthlyPayload = document.getElementById('monthly-data');
  if (monthlyEl && monthlyPayload) {
    const data = JSON.parse(monthlyPayload.textContent);
    new Chart(monthlyEl, {
      type: 'bar',
      data: {
        labels: data.labels,
        datasets: [
          {
            label: 'Total mensual',
            data: data.values,
            borderRadius: 8,
            backgroundColor: data.labels.map((_, i) => PALETTE[i % PALETTE.length]),
          },
        ],
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: {
          y: {
            beginAtZero: true,
            ticks: { callback: currencyFmt },
          },
        },
      },
    });
  }

  /* ── Category pie chart (client detail) ─────────────────── */
  const catEl = document.getElementById('categoryChart');
  const catPayload = document.getElementById('category-data');
  if (catEl && catPayload) {
    const data = JSON.parse(catPayload.textContent);
    new Chart(catEl, {
      type: 'doughnut',
      data: {
        labels: data.labels,
        datasets: [
          {
            data: data.values,
            backgroundColor: data.labels.map((_, i) => PALETTE[i % PALETTE.length]),
            borderWidth: 2,
            borderColor: '#fff',
          },
        ],
      },
      options: {
        responsive: true,
        plugins: {
          legend: {
            position: 'bottom',
            labels: { font: { family: 'Outfit', size: 11 }, padding: 12 },
          },
          tooltip: {
            callbacks: {
              label(ctx) {
                const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                const pct = total ? ((ctx.parsed / total) * 100).toFixed(1) : 0;
                return ` ${currencyFmt(ctx.parsed)} (${pct}%)`;
              },
            },
          },
        },
      },
    });
  }
});
