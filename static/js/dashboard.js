async function loadDashboardData() {
  try {
    const response = await fetch('/api/dashboard');
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Unable to load dashboard analytics.');

    if (!data.kpis || data.kpis.total_records === 0) return;

    renderBarChart('cropChart', 'Crop-wise modal-price comparison', data.kpis.crop_data || [], 'commodity', 'average_modal_price');
    renderBarChart('marketChart', 'Market-wise price comparison', data.kpis.market_data || [], 'market', 'average_price');
    renderComparisonChart('cropPriceRangeChart', data.kpis.crop_price_comparison || [], 'commodity', [
      { key: 'average_min_price', label: 'Average minimum', color: '#86c98a' },
      { key: 'average_modal_price', label: 'Average modal', color: '#228b22' },
      { key: 'average_max_price', label: 'Average maximum', color: '#f4c542' },
    ]);
    renderBarChart('districtPriceChart', 'Average modal price by district', data.kpis.district_price_data || [], 'district', 'average_modal_price');
    renderComparisonChart('marketPriceRangeChart', data.kpis.market_price_ranges || [], 'market', [
      { key: 'average_min_price', label: 'Average minimum', color: '#86c98a' },
      { key: 'average_max_price', label: 'Average maximum', color: '#f4c542' },
    ]);
    renderLineChart('trendChart', 'Historical price trend', data.kpis.trend_data || [], 'arrival_date', 'average_modal_price');
  } catch (error) {
    const notice = document.getElementById('dashboardDataNotice');
    if (notice) {
      notice.textContent = error.message;
      notice.classList.remove('d-none');
    }
  }
}

function renderComparisonChart(canvasId, records, labelKey, series) {
  const ctx = document.getElementById(canvasId);
  if (!ctx || records.length === 0) return;

  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: records.map((item) => item[labelKey]),
      datasets: series.map((item) => ({
        label: item.label,
        data: records.map((record) => record[item.key] === null ? null : Number(record[item.key])),
        backgroundColor: item.color,
        borderRadius: 5,
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { position: 'bottom' } },
      scales: { y: { beginAtZero: false, ticks: { maxTicksLimit: 6 } } },
    },
  });
}

function renderBarChart(canvasId, title, records, labelKey, valueKey) {
  const ctx = document.getElementById(canvasId);
  if (!ctx || records.length === 0) return;

  const labels = records.map((item) => item[labelKey]);
  const values = records.map((item) => Number(item[valueKey] || 0));

  new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: title,
        data: values,
        backgroundColor: ['#14532D', '#228B22', '#F4C542', '#F97316', '#8B5E3C', '#4ADE80'],
        borderRadius: 8,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: false } }
    }
  });
}

function renderLineChart(canvasId, title, records, labelKey, valueKey) {
  const ctx = document.getElementById(canvasId);
  if (!ctx || records.length === 0) return;

  const labels = records.map((item) => item[labelKey]);
  const values = records.map((item) => Number(item[valueKey] || 0));

  new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: title,
        data: values,
        borderColor: '#14532D',
        backgroundColor: 'rgba(20, 83, 45, 0.12)',
        fill: true,
        tension: 0.35,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: false } }
    }
  });
}

window.addEventListener('DOMContentLoaded', loadDashboardData);
