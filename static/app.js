/* ── Token helpers ── */
const getToken = () => localStorage.getItem('era5_token');
const setToken = (t) => localStorage.setItem('era5_token', t);
const clearToken = () => localStorage.removeItem('era5_token');

/* ── Auth guard (call on protected pages) ── */
function requireAuth() {
  if (!getToken()) { window.location.href = '/'; return false; }
  return true;
}

/* ── API fetch wrapper ── */
async function apiCall(method, endpoint, body = null) {
  const headers = { 'Content-Type': 'application/json' };
  const token = getToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const opts = { method, headers };
  if (body) opts.body = JSON.stringify(body);

  const res = await fetch(`/api${endpoint}`, opts);
  const data = await res.json();
  return { ok: res.ok, status: res.status, data };
}

/* ── Toast notification ── */
function showToast(msg, type = 'info') {
  let toast = document.getElementById('toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'toast';
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  toast.className = `show ${type}`;
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => toast.className = '', 3500);
}

/* ── Active nav link ── */
function setActiveNav() {
  const path = window.location.pathname;
  const map = {
    '/dashboard':    'nav-dashboard',
    '/request-page': 'nav-request',
    '/history':      'nav-history',
    '/convert-csv':  'nav-convert',
    '/profile':      'nav-profile',
  };
  const id = map[path];
  if (id) document.getElementById(id)?.classList.add('active');
}

/* ── Load user info into nav ── */
async function loadUserInfo() {
  const r = await apiCall('GET', '/me');
  if (!r.ok) { clearToken(); window.location.href = '/'; return; }
  const user = r.data.user;

  const nameEl = document.getElementById('nav-user-name');
  if (nameEl) nameEl.textContent = user.name;

  return user;
}

/* ── Logout ── */
function logout() {
  clearToken();
  window.location.href = '/';
}

/* ── Badge HTML ── */
function statusBadge(status) {
  const map = {
    'Pending':    'badge-pending',
    'Processing': 'badge-processing',
    'Completed':  'badge-completed',
    'Failed':     'badge-failed',
  };
  return `<span class="badge ${map[status] || ''}">${status}</span>`;
}

/* ── Download link ── */
function downloadBtn(reqId, type, label, disabled) {
  if (disabled) return `<span style="color:var(--muted);font-size:11px">${label}</span>`;
  return `<a href="#" onclick="downloadFile(${reqId},'${type}');return false;" class="btn btn-sm btn-green">${label}</a>`;
}

/* ── Download a file using the JWT-protected endpoint ── */
async function downloadFile(reqId, fileType) {
  const token = getToken();
  const res = await fetch(`/api/download/${reqId}/${fileType}`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  if (!res.ok) { showToast('File not ready yet', 'error'); return; }
  const blob = await res.blob();
  const cd = res.headers.get('Content-Disposition') || '';
  const match = cd.match(/filename="?([^"]+)"?/);
  const fname = match ? match[1] : `download_${reqId}_${fileType}`;
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = fname; a.click();
  URL.revokeObjectURL(url);
}