'use strict';

const $ = id => document.getElementById(id);
// Master credential stays in memory; refresh locks the console.
let key = '';
function writeSession(value){ key=value; }
let snapshot = null;
let selectedWallet = '';

const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}[c]));
const num = value => new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 2 }).format(Number(value || 0));
const usd = value => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(Number(value || 0));
const gnk = value => (Number(value || 0) / 1e9).toLocaleString(undefined, { maximumFractionDigits: 4 }) + ' GNK';

function notice(message) {
  $('notice').textContent = message;
  clearTimeout(notice.timer);
  notice.timer = setTimeout(() => { $('notice').textContent = ''; }, 6500);
}

async function api(path, options = {}) {
  const headers = {
    Authorization: 'Bearer ' + key,
    ...(options.body ? { 'Content-Type': 'application/json' } : {}),
    ...options.headers,
  };
  const response = await fetch(path, { ...options, headers, credentials: 'same-origin' });
  let data = {};
  try { data = await response.json(); } catch {}
  if (!response.ok) {
    const error = new Error(data.error?.message || response.statusText);
    error.status = response.status;
    throw error;
  }
  return data;
}

function metric(label, value, cls = '') {
  return `<div class="metric ${cls}"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`;
}
function table(headers, rows) {
  return `<table><thead><tr>${headers.map(h => `<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.join('') || `<tr><td colspan="${headers.length}" class="muted">No records</td></tr>`}</tbody></table>`;
}

function render(overview) {
  snapshot = overview;
  const providerBalance = overview.provider_balance;
  const providerTotals = overview.provider_usage?.totals || {};
  const local = overview.local || {};
  const pool = overview.pool || {};
  const capacity = overview.fund_capacity || {};
  const economics = overview.economics || {};
  const days = overview.window_days || 30;

  $('metrics').innerHTML = [
    metric('OpenBroker available', providerBalance ? gnk(providerBalance.available_ngonka) : 'Unavailable', providerBalance ? '' : 'bad'),
    metric('Funded AI tokens', capacity.local_available_ai_tokens == null ? '—' : num(capacity.local_available_ai_tokens)),
    metric('Member-days funded', capacity.wallet_days_at_full_allowance == null ? '—' : num(capacity.wallet_days_at_full_allowance)),
    metric(`${days}d local tokens`, num(local.tokens)),
    metric(`${days}d provider cost`, Number.isFinite(providerTotals.cost_ngonka) ? gnk(providerTotals.cost_ngonka) : 'Unavailable'),
    metric('Usage value · not collected revenue', usd(economics.metered_revenue_reference_usd)),
    metric('Runway', overview.runway_days_at_recent_provider_spend == null ? '—' : overview.runway_days_at_recent_provider_spend + ' days'),
  ].join('');

  const provider = overview.provider_status;
  $('provider-state').textContent = provider?.status || 'unavailable';
  $('provider-state').className = 'pill ' + ((provider?.status === 'ok' || provider?.status === 'healthy') ? 'good' : 'bad');
  const models = provider?.models || [];
  $('model-health').innerHTML = table(['Model', 'Status', 'Routable', 'Capacity', 'Load', 'In flight', 'Policy'], models.map(model => {
    const disabled = (overview.config.disabled_models || []).includes(model.model);
    return `<tr><td>${esc(model.model)}</td><td class="${model.status === 'healthy' ? 'good' : 'bad'}">${esc(model.status)}</td><td>${model.routable === true ? 'yes' : 'no'}</td><td>${esc(model.capacity_available_pct ?? '—')}%</td><td>${esc(model.load_pct ?? '—')}%</td><td>${esc(model.in_flight_requests ?? '—')}</td><td><button class="small-action model-toggle" data-model="${esc(model.model)}">${disabled ? 'Enable' : 'Disable'}</button></td></tr>`;
  }));

  $('fund-summary').innerHTML = `<div class="metrics compact">${[
    metric('Allocated', gnk(pool.allocated_ngonka)),
    metric('Spent', gnk(pool.budget_spent_ngonka)),
    metric('Held', gnk(pool.reserved_ngonka)),
    metric('Available AI tokens', capacity.local_available_ai_tokens == null ? '—' : num(capacity.local_available_ai_tokens)),
    metric('Budget rate', capacity.budget_ngonka_per_token == null ? '—' : capacity.budget_ngonka_per_token + ' ngonka/token'),
    metric('Broker capacity', capacity.broker_available_ai_tokens == null ? '—' : num(capacity.broker_available_ai_tokens) + ' tokens'),
  ].join('')}</div>`;

  const config = overview.config;
  document.querySelectorAll('#settings-form [data-k]').forEach(input => {
    const value = config[input.dataset.k];
    if (input.type === 'checkbox') input.checked = !!value;
    else input.value = value ?? '';
  });
  $('price-input').value = config.retail_input_per_million_usd;
  $('price-output').value = config.retail_output_per_million_usd;

  const business = overview.business;
  $('business-net').textContent = usd(business.cash_net_usd);
  $('business-summary').innerHTML = [
    metric('Recorded revenue', usd(business.revenue_usd)),
    metric('Recorded expenses', usd(business.expense_usd)),
    metric('Net cash ledger', usd(business.cash_net_usd)),
    metric('Provider compute', economics.provider_cost_usd == null ? (Number.isFinite(providerTotals.cost_ngonka) ? gnk(providerTotals.cost_ngonka) : 'Unavailable') : usd(economics.provider_cost_usd)),
    metric('Modeled contribution', economics.compute_contribution_reference_usd == null ? 'Set GNK/USD' : usd(economics.compute_contribution_reference_usd)),
    metric('Modeled compute margin', economics.compute_margin_reference_pct == null ? '—' : economics.compute_margin_reference_pct.toFixed(1) + '%'),
  ].join('');
  $('business-table').innerHTML = table(['Date', 'Category', 'Amount', 'Reference'], (business.recent || []).slice(0, 20).map(entry =>
    `<tr><td>${new Date(entry.created * 1000).toLocaleDateString()}</td><td>${esc(entry.category)}</td><td class="${entry.amount_usd >= 0 ? 'good' : 'bad'}">${usd(entry.amount_usd)}</td><td>${esc(entry.reference)}</td></tr>`
  ));

  document.querySelectorAll('.model-toggle').forEach(button => {
    button.onclick = async () => {
      try {
        const current = new Set(snapshot.config.disabled_models || []);
        current.has(button.dataset.model) ? current.delete(button.dataset.model) : current.add(button.dataset.model);
        await saveConfig([...current]);
        await load();
        notice('Model policy updated.');
      } catch (error) { notice(error.message); }
    };
  });
}

async function loadUsers() {
  const query = $('user-search').value.trim();
  const result = await api('/api/admin/users?limit=100&q=' + encodeURIComponent(query));
  $('user-count').textContent = result.data.length + (query ? ' matches' : ' shown');
  $('users').innerHTML = table(['Wallet', 'Keys', 'Requests', 'AI tokens', 'GNK cost', 'Status', 'Manage'], result.data.map(user =>
    `<tr><td class="wallet" title="${esc(user.wallet)}">${esc(user.wallet)}</td><td>${user.active_keys}</td><td>${user.requests}</td><td>${num(user.tokens)}</td><td>${gnk(user.cost_ngonka)}</td><td>${user.disabled ? '<span class="bad">disabled</span>' : '<span class="good">active</span>'}</td><td><button class="small-action user-manage" data-wallet="${esc(user.wallet)}">Manage</button></td></tr>`
  ));
  document.querySelectorAll('.user-manage').forEach(button => {
    button.onclick = () => manageUser(button.dataset.wallet, result.data.find(user => user.wallet === button.dataset.wallet));
  });
}

async function manageUser(wallet, user) {
  selectedWallet = wallet;
  $('user-detail').hidden = false;
  $('user-detail-title').textContent = wallet;
  $('user-disabled').checked = !!user.disabled;
  $('user-daily').value = user.daily_tokens_override ?? '';
  $('user-note').value = user.note || '';
  const result = await api('/api/admin/users/' + encodeURIComponent(wallet) + '/keys');
  $('user-keys').innerHTML = table(['Prefix', 'Name', 'Created', 'Status', 'Action'], result.data.map(item =>
    `<tr><td><code>${esc(item.prefix)}</code></td><td>${esc(item.name)}</td><td>${new Date(item.created * 1000).toLocaleDateString()}</td><td>${item.revoked ? '<span class="bad">revoked</span>' : '<span class="good">active</span>'}</td><td>${item.revoked ? '—' : `<button class="small-action revoke-key" data-id="${esc(item.id)}">Revoke</button>`}</td></tr>`
  ));
  document.querySelectorAll('.revoke-key').forEach(button => {
    button.onclick = async () => {
      if (!confirm('Revoke this API key immediately?')) return;
      try {
        await api('/api/admin/users/' + encodeURIComponent(wallet) + '/keys/' + encodeURIComponent(button.dataset.id), { method: 'DELETE' });
        await manageUser(wallet, user);
        await loadAudit();
        notice('API key revoked.');
      } catch (error) { notice(error.message); }
    };
  });
}

async function loadRequests() {
  const result = await api('/api/admin/requests');
  $('requests').innerHTML = table(['Time', 'Wallet', 'Model', 'State', 'Tokens', 'Cost'], result.data.map(item =>
    `<tr><td>${new Date(item.created * 1000).toLocaleString()}</td><td class="wallet" title="${esc(item.wallet)}">${esc(item.wallet)}</td><td>${esc(item.model.split('/').pop())}</td><td>${esc(item.state)}</td><td>${num(item.tokens || item.reserved_tokens)}</td><td>${gnk(item.cost_ngonka || item.reserved_ngonka)}</td></tr>`
  ));
}

async function loadAudit() {
  const result = await api('/api/admin/audit?limit=100');
  $('audit-log').innerHTML = table(['Time', 'Action', 'Target', 'Note'], result.data.map(item =>
    `<tr><td>${new Date(item.created * 1000).toLocaleString()}</td><td>${esc(item.action)}</td><td class="wallet" title="${esc(item.target)}">${esc(item.target)}</td><td>${esc(item.note)}</td></tr>`
  ));
}

async function load() {
  const days = Number($('window-days').value) || 30;
  const [overview] = await Promise.all([
    api('/api/admin/overview?days=' + days),
    loadUsers(), loadRequests(), loadAudit(),
  ]);
  render(overview);
  if (typeof loadConnections === 'function') await loadConnections();
  if (typeof loadReadiness === 'function') await loadReadiness();
}

function configPayload(disabled) {
  const payload = {};
  document.querySelectorAll('#settings-form [data-k]').forEach(input => {
    payload[input.dataset.k] = input.type === 'checkbox' ? input.checked : (input.dataset.k === 'gnk_usd' ? (input.value || null) : Number(input.value));
  });
  payload.retail_input_nusd_per_token = Math.round(Number($('price-input').value) * 1000);
  payload.retail_output_nusd_per_token = Math.round(Number($('price-output').value) * 1000);
  payload.disabled_models = disabled ?? snapshot?.config?.disabled_models ?? [];
  return payload;
}
async function saveConfig(disabled) {
  return api('/api/admin/config', { method: 'PUT', body: JSON.stringify(configPayload(disabled)) });
}
async function unlock() {
  key = $('admin-key').value.trim() || key;
  if (!key) return;
  $('login-msg').textContent = 'Checking…';
  try {
    await api('/api/admin/config');
    writeSession(key);
    $('admin-key').value='';
    $('login').hidden = true;
    $('console').hidden = false;
    await load();
  } catch (error) { $('login-msg').textContent = error.message; }
}

$('unlock').onclick = unlock;
$('admin-key').addEventListener('keydown', event => { if (event.key === 'Enter') unlock(); });
$('logout').onclick = () => { writeSession(''); location.reload(); };
$('refresh').onclick = () => load().catch(error => notice(error.message));
$('window-days').onchange = () => load().catch(error => notice(error.message));
$('save-config').onclick = async () => { try { await saveConfig(); await load(); notice('Runtime policy saved.'); } catch (error) { notice(error.message); } };
$('fund-form').onsubmit = async event => {
  event.preventDefault();
  try {
    await api('/api/admin/allowance/fund', { method: 'POST', body: JSON.stringify({ gnk: $('fund-gnk').value, reference: $('fund-ref').value, confirm_funded: true }) });
    event.target.reset(); await load(); notice('Local GNK allocation recorded. No crypto was moved.');
  } catch (error) { notice(error.message); }
};
$('business-form').onsubmit = async event => {
  event.preventDefault();
  try {
    await api('/api/admin/business', { method: 'POST', body: JSON.stringify({ category: $('biz-category').value, amount_usd: $('biz-amount').value, reference: $('biz-ref').value, note: $('biz-note').value }) });
    event.target.reset(); await load(); notice('Business ledger entry recorded.');
  } catch (error) { notice(error.message); }
};
$('user-search-btn').onclick = () => loadUsers().catch(error => notice(error.message));
$('user-search').addEventListener('keydown', event => { if (event.key === 'Enter') { event.preventDefault(); loadUsers().catch(error => notice(error.message)); } });
$('user-detail-close').onclick = () => { $('user-detail').hidden = true; selectedWallet = ''; };
$('user-policy-form').onsubmit = async event => {
  event.preventDefault();
  if (!selectedWallet) return;
  try {
    const daily = $('user-daily').value.trim();
    await api('/api/admin/users/' + encodeURIComponent(selectedWallet), { method: 'PUT', body: JSON.stringify({ disabled: $('user-disabled').checked, daily_tokens_override: daily ? Number(daily) : null, note: $('user-note').value }) });
    await loadUsers(); await loadAudit(); notice('User policy updated.');
  } catch (error) { notice(error.message); }
};
if (key) { $('admin-key').value = key; unlock(); }
