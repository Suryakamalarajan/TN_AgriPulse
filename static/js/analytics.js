async function loadAnalyticsData() {
  const response = await fetch('/api/analytics');
  const data = await response.json();

  if (!data || data.status === 'empty') {
    document.getElementById('analyticsEmpty').classList.remove('d-none');
    return;
  }

  renderBarChart('cropAverageChart', data.crop_averages || [], 'commodity', 'average_modal_price');
  renderBarChart('marketDifferenceChart', data.market_differences || [], 'commodity', 'difference');
  renderLineChart('trendHistoryChart', data.historical_trends || [], 'arrival_date', 'average_modal_price');
}

function renderBarChart(canvasId, records, labelKey, valueKey) {
  const ctx = document.getElementById(canvasId);
  if (!ctx || !records.length) return;

  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: records.map((item) => item[labelKey]),
      datasets: [{
        label: 'Average Price',
        data: records.map((item) => Number(item[valueKey] || 0)),
        backgroundColor: ['#14532D', '#228B22', '#F4C542', '#F97316', '#8B5E3C', '#4ADE80'],
        borderRadius: 8,
      }],
    },
    options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: false } } }
  });
}

function renderLineChart(canvasId, records, labelKey, valueKey) {
  const ctx = document.getElementById(canvasId);
  if (!ctx || !records.length) return;

  new Chart(ctx, {
    type: 'line',
    data: {
      labels: records.map((item) => item[labelKey]),
      datasets: [{
        label: 'Historical Trend',
        data: records.map((item) => Number(item[valueKey] || 0)),
        borderColor: '#228B22',
        fill: false,
        tension: 0.25,
      }],
    },
    options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: false } } }
  });
}

window.addEventListener('DOMContentLoaded', loadAnalyticsData);
