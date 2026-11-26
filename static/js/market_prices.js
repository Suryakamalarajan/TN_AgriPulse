let currentPage = 1;
const pageSize = 10;
const canManageRecords = Boolean(window.marketRecordsCanManage);

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[character]));
}

function csrfHeaders() {
  const token = document.querySelector('meta[name="csrf-token"]')?.content || '';
  return { 'X-CSRFToken': token };
}

function showNotice(message, type = 'success') {
  const notice = document.getElementById('marketRecordsNotice');
  notice.className = `alert alert-${type}`;
  notice.textContent = message;
  notice.classList.remove('d-none');
}

function hideNotice() {
  const notice = document.getElementById('marketRecordsNotice');
  notice.classList.add('d-none');
}

function updateExportLink() {
  const exportLink = document.getElementById('exportCsvBtn');
  if (!exportLink) return;
  const formData = new FormData(document.getElementById('filterForm'));
  const params = new URLSearchParams();
  for (const [key, value] of formData.entries()) {
    if (value) params.set(key, value);
  }
  exportLink.href = `/export/csv?${params.toString()}`;
}

function renderTable(records, demoRecordCount = 0) {
  const tbody = document.getElementById('marketRecordsBody');
  const columnCount = Number(tbody.dataset.columnCount);
  const demoNotice = document.getElementById('demoDataNotice');
  if (demoNotice) {
    demoNotice.classList.toggle(
      'd-none',
      Number(demoRecordCount) === 0
        && !records.some((record) => String(record.source || '').toUpperCase() === 'DEMO'),
    );
  }
  if (!records.length) {
    tbody.innerHTML = `<tr><td colspan="${columnCount}" class="text-center text-muted py-4">No market price records match your filters.</td></tr>`;
    return;
  }

  tbody.innerHTML = records.map((record) => {
    const price = (value) => value === null || value === undefined || value === ''
      ? '—'
      : `₹${Number(value).toFixed(2)}`;
    const status = String(record.verification_status || 'unverified').toLowerCase();
    const statusClass = status === 'verified' ? 'text-bg-success' : (status === 'pending' ? 'text-bg-warning' : 'text-bg-secondary');
    const actions = canManageRecords ? `
      <td class="text-nowrap">
        <button type="button" class="btn btn-sm btn-outline-success me-1" data-action="edit" data-id="${Number(record.id)}" aria-label="Edit record">
          <i class="bi bi-pencil" aria-hidden="true"></i>
        </button>
        <button type="button" class="btn btn-sm btn-outline-danger" data-action="delete" data-id="${Number(record.id)}" aria-label="Delete record">
          <i class="bi bi-trash" aria-hidden="true"></i>
        </button>
      </td>` : '';

    return `
      <tr>
        <td>${escapeHtml(record.state)}</td>
        <td>${escapeHtml(record.district)}</td>
        <td>${escapeHtml(record.market)}</td>
        <td>${escapeHtml(record.commodity)}</td>
        <td>${escapeHtml(record.variety || '—')}</td>
        <td>${escapeHtml(record.arrival_date || '')}</td>
        <td>${price(record.min_price)}</td>
        <td>${price(record.max_price)}</td>
        <td>${price(record.modal_price)}</td>
        <td>${escapeHtml(record.price_unit || 'INR/Qtl')}</td>
        <td>${String(record.source || '').toUpperCase() === 'DEMO'
          ? '<span class="badge text-bg-warning">DEMO</span>'
          : escapeHtml(record.source || 'Unknown')}</td>
        <td><span class="badge ${statusClass}">${escapeHtml(status)}</span></td>
        <td>${escapeHtml(record.fetched_at || '')}</td>
        ${actions}
      </tr>`;
  }).join('');
}

function renderPagination(page, totalPages) {
  const pagination = document.getElementById('pagination');
  if (totalPages <= 1) {
    pagination.innerHTML = '';
    return;
  }

  const firstPage = Math.max(1, Math.min(page - 2, totalPages - 4));
  const lastPage = Math.min(totalPages, firstPage + 4);
  const buttons = [];
  buttons.push(`
    <li class="page-item ${page === 1 ? 'disabled' : ''}">
      <button class="page-link" data-page="${page - 1}" type="button" aria-label="Previous page">‹</button>
    </li>`);
  for (let number = firstPage; number <= lastPage; number += 1) {
    buttons.push(`
      <li class="page-item ${number === page ? 'active' : ''}">
        <button class="page-link" data-page="${number}" type="button" ${number === page ? 'aria-current="page"' : ''}>${number}</button>
      </li>`);
  }
  buttons.push(`
    <li class="page-item ${page === totalPages ? 'disabled' : ''}">
      <button class="page-link" data-page="${page + 1}" type="button" aria-label="Next page">›</button>
    </li>`);
  pagination.innerHTML = buttons.join('');
}

async function fetchMarketRecords(page = 1) {
  const form = document.getElementById('filterForm');
  const formData = new FormData(form);
  const params = new URLSearchParams({ page: String(page), limit: String(pageSize) });
  for (const [key, value] of formData.entries()) {
    if (value) params.set(key, value);
  }

  const tbody = document.getElementById('marketRecordsBody');
  tbody.innerHTML = `<tr><td colspan="${tbody.dataset.columnCount}" class="text-center py-4"><span class="spinner-border spinner-border-sm text-success me-2" role="status" aria-hidden="true"></span>Loading market records...</td></tr>`;
  try {
    const response = await fetch(`/api/market-records?${params.toString()}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Unable to load market records.');
    if (page > data.pages) {
      await fetchMarketRecords(data.pages);
      return;
    }

    currentPage = data.page;
    renderTable(data.records, data.demo_records);
    renderPagination(data.page, data.pages);
    document.getElementById('recordsInfo').textContent = `Showing ${data.records.length} of ${data.total} records`;
  } catch (error) {
    tbody.innerHTML = `<tr><td colspan="${tbody.dataset.columnCount}" class="text-center text-danger py-4">${escapeHtml(error.message)}</td></tr>`;
    document.getElementById('recordsInfo').textContent = '';
  }
}

async function refreshFilterOptions() {
  const response = await fetch('/api/filters');
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Unable to refresh filter options.');

  for (const [field, values] of Object.entries({
    district: data.district || [],
    commodity: data.commodity || [],
    market: data.market || [],
  })) {
    const select = document.getElementById(field);
    const selected = select.value;
    const allLabel = field === 'commodity' ? 'All crops' : `All ${field}s`;
    select.replaceChildren(new Option(allLabel, ''));
    values.forEach((value) => select.add(new Option(value, value)));
    if (values.includes(selected)) select.value = selected;
  }
}

async function reloadRecordsAfterChange(page) {
  try {
    await refreshFilterOptions();
  } catch (error) {
    showNotice(`Market record changed, but filter options could not be refreshed: ${error.message}`, 'warning');
  }
  await fetchMarketRecords(page);
}

function showFormError(message) {
  const error = document.getElementById('marketRecordFormError');
  error.textContent = message;
  error.classList.remove('d-none');
}

function setFormBusy(busy) {
  const button = document.getElementById('saveMarketRecordBtn');
  button.disabled = busy;
  button.querySelector('.spinner-border').classList.toggle('d-none', !busy);
  button.querySelector('.submit-label').textContent = busy ? 'Saving...' : 'Save Record';
}

window.addEventListener('DOMContentLoaded', () => {
  const filterForm = document.getElementById('filterForm');
  fetchMarketRecords(1);

  filterForm.addEventListener('submit', (event) => {
    event.preventDefault();
    const from = document.getElementById('date_from').value;
    const to = document.getElementById('date_to').value;
    if (from && to && from > to) {
      showNotice('Arrival from date cannot be later than arrival to date.', 'warning');
      return;
    }
    hideNotice();
    updateExportLink();
    fetchMarketRecords(1);
  });

  document.getElementById('resetFiltersBtn').addEventListener('click', () => {
    filterForm.reset();
    hideNotice();
    updateExportLink();
    fetchMarketRecords(1);
  });
  updateExportLink();

  document.getElementById('pagination').addEventListener('click', (event) => {
    const button = event.target.closest('button[data-page]');
    if (!button || button.closest('.disabled')) return;
    fetchMarketRecords(Number(button.dataset.page));
  });

  if (!canManageRecords) return;

  const modalElement = document.getElementById('marketRecordModal');
  const modal = new bootstrap.Modal(modalElement);
  const form = document.getElementById('marketRecordForm');

  function resetRecordForm() {
    form.reset();
    form.elements.record_id.value = '';
    form.elements.price_unit.value = 'INR/Qtl';
    form.elements.source.value = 'Manual entry';
    form.elements.verification_status.value = 'unverified';
    const today = new Date();
    form.elements.arrival_date.value = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
    document.getElementById('marketRecordFormError').classList.add('d-none');
    document.getElementById('marketRecordModalTitle').textContent = 'Add Market Price';
  }

  document.getElementById('addMarketRecordBtn').addEventListener('click', () => {
    resetRecordForm();
    modal.show();
  });

  modalElement.addEventListener('hidden.bs.modal', resetRecordForm);

  document.getElementById('marketRecordsBody').addEventListener('click', async (event) => {
    const button = event.target.closest('button[data-action]');
    if (!button) return;
    const recordId = Number(button.dataset.id);
    if (!Number.isInteger(recordId) || recordId < 1) return;

    if (button.dataset.action === 'edit') {
      try {
        const response = await fetch(`/api/market-records/${recordId}`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Unable to load this record.');
        resetRecordForm();
        document.getElementById('marketRecordModalTitle').textContent = 'Edit Market Price';
        for (const [field, value] of Object.entries(data.record)) {
          if (form.elements[field]) form.elements[field].value = value ?? '';
        }
        form.elements.record_id.value = String(recordId);
        modal.show();
      } catch (error) {
        showNotice(error.message, 'danger');
      }
      return;
    }

    if (button.dataset.action === 'delete'
      && window.confirm('Delete this market price record? This action cannot be undone.')) {
      button.disabled = true;
      try {
        const response = await fetch(`/api/market-records/${recordId}`, {
          method: 'DELETE',
          headers: csrfHeaders(),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Unable to delete this record.');
        showNotice(data.message);
        await reloadRecordsAfterChange(currentPage);
      } catch (error) {
        showNotice(error.message, 'danger');
        button.disabled = false;
      }
    }
  });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const errorBox = document.getElementById('marketRecordFormError');
    errorBox.classList.add('d-none');
    const values = Object.fromEntries(new FormData(form).entries());
    const recordId = values.record_id;
    delete values.record_id;
    setFormBusy(true);

    try {
      const response = await fetch(recordId ? `/api/market-records/${recordId}` : '/api/market-records', {
        method: recordId ? 'PUT' : 'POST',
        headers: { ...csrfHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify(values),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Unable to save this record.');

      modal.hide();
      showNotice(data.message);
      await reloadRecordsAfterChange(recordId ? currentPage : 1);
    } catch (error) {
      showFormError(error.message);
    } finally {
      setFormBusy(false);
    }
  });
});
