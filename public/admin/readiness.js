/* Read-only launch checklist. Shares the in-memory admin session, never credentials. */
'use strict';
async function loadReadiness(parent = () => true) {
  const isCurrent = nextRefresh('readiness', parent);
  const target = document.getElementById('readiness-list');
  if (!target) return;
  try {
    const data = await api('/api/admin/readiness');
    if (!isCurrent()) return;
    document.getElementById('readiness-state').textContent = data.status === 'blocked' ? 'Setup incomplete' : 'Review required';
    target.replaceChildren();
    for (const item of data.checks || []) {
      const row = document.createElement('li');
      const title = document.createElement('strong'); title.textContent = item.title;
      const state = document.createElement('span'); state.className = 'pill'; state.textContent = item.status;
      const detail = document.createElement('p'); detail.textContent = item.detail;
      row.append(title, state, detail); target.append(row);
    }
    document.getElementById('readiness-capacity').textContent = `${data.capacity.full_allowances_per_day} full default allowances fit in the current daily pool. This is not guaranteed capacity for every holder.`;
    document.getElementById('readiness-accounting').textContent = data.accounting_notice;
    document.getElementById('readiness-time').textContent = 'Configuration checked ' + new Date(data.checked_at * 1000).toLocaleTimeString() + ' · no funds spent';
  } catch (error) {
    if (!isCurrent()) return;
    document.getElementById('readiness-state').textContent = 'Unavailable';
    target.replaceChildren();
    const row = document.createElement('li'); row.textContent = error.message; target.append(row);
    for (const id of ['readiness-capacity','readiness-accounting','readiness-time']) document.getElementById(id).textContent = '';
  }
}
document.getElementById('readiness-refresh')?.addEventListener('click', () => loadReadiness());
