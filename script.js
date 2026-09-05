// B_gadget POS - Hybrid: FastAPI + SQLite, fallback localStorage
const STORAGE_KEY = 'servicell_data_v1';
const API_BASE = (() => {
  const stored = localStorage.getItem('API_BASE');
  if (stored) return stored;
  const host = location.hostname;
  if (host === 'localhost' || host === '127.0.0.1') return 'http://localhost:8000/api';
  return location.origin + '/api'; // service.reneepsl.my.id via tunnel
})();
let USE_API = true; // coba API dulu, fallback ke localStorage jika gagal

const defaultData = [
  {id:'INV-2026-0118', invoice:'INV-2026-0118', nama:'Renee Budiman', wa:'081234567890', device:'iPhone 11 64GB', keluhan:'LCD pecah & baterai drop', teknisi:'Andi', biaya:850000, status:'Dikerjakan', date:'2026-09-02', kelengkapan:['HP Saja','+ Charger']},
  {id:'INV-2026-0119', invoice:'INV-2026-0119', nama:'Dewi Lestari', wa:'082112345678', device:'Samsung A54', keluhan:'Mati total habis jatuh', teknisi:'Sinta', biaya:450000, status:'Antri', date:'2026-09-02', kelengkapan:['HP Saja']},
  {id:'INV-2026-0120', invoice:'INV-2026-0120', nama:'Budi Santoso', wa:'081345678901', device:'Xiaomi Redmi Note 12', keluhan:'Kamera belakang blur', teknisi:'Budi', biaya:250000, status:'Menunggu Sparepart', date:'2026-09-01', kelengkapan:['HP Saja','+ Dus']},
  {id:'INV-2026-0121', invoice:'INV-2026-0121', nama:'Citra Amelia', wa:'085678901234', device:'Oppo Reno 8', keluhan:'Speaker sember', teknisi:'Andi', biaya:180000, status:'Selesai', date:'2026-09-01', kelengkapan:['HP Saja']},
  {id:'INV-2026-0122', invoice:'INV-2026-0122', nama:'Fajar Pratama', wa:'081987654321', device:'iPhone XR', keluhan:'Face ID tidak berfungsi', teknisi:'Sinta', biaya:650000, status:'Antri', date:'2026-09-02', kelengkapan:['HP Saja','+ Charger']},
];

let data = [];

function computeDeadline(dateStr, dtype){
  if(!dateStr) return null;
  const d = new Date(dateStr);
  const days = dtype === 'mingguan' ? 7 : 3;
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0,10);
}
function computeSisa(deadlineStr){
  if(!deadlineStr) return null;
  const today = new Date(); today.setHours(0,0,0,0);
  const dl = new Date(deadlineStr); dl.setHours(0,0,0,0);
  return Math.round((dl - today)/86400000);
}
function normalize(item){
  // backend -> frontend shape
  const dtype = (item.deadline_type || 'harian').toLowerCase();
  let dl = item.deadline || null;
  if(!dl && item.date){
    dl = computeDeadline(item.date, dtype);
  }
  let sisa = item.sisa_hari;
  if(sisa === undefined || sisa === null) sisa = dl ? computeSisa(dl) : null;
  let overdue = item.is_overdue;
  if(overdue === undefined || overdue === null){
    overdue = sisa !== null ? (sisa < 0 && !['Selesai','Sudah Diambil','Dibatalkan','Service Failed'].includes(item.status)) : false;
  }
  return {
    id: item.invoice || item.id,
    invoice: item.invoice || item.id,
    nama: item.nama,
    wa: item.wa,
    device: item.device,
    keluhan: item.keluhan,
    teknisi: item.teknisi || item.technician || '-',
    biaya: item.biaya || 0,
    status: item.status,
    date: (item.date || '').slice(0,10),
    kelengkapan: Array.isArray(item.kelengkapan) ? item.kelengkapan : (typeof item.kelengkapan === 'string' ? JSON.parse(item.kelengkapan || '[]') : []),
    estimasi_selesai: item.estimasi_selesai || null,
    deadline_type: dtype,
    deadline: dl,
    sisa_hari: sisa,
    is_overdue: overdue
  };
}

function updateDeadlinePreview(){
  const sel = document.getElementById('f-deadline-type');
  const prev = document.getElementById('deadlinePreview');
  if(!sel || !prev) return;
  const dtype = sel.value;
  const days = dtype === 'mingguan' ? 7 : 3;
  const today = new Date();
  const dl = new Date(today); dl.setDate(today.getDate()+days);
  prev.textContent = `Deadline: ${dl.toLocaleDateString('id-ID')} (${days} hari dari hari ini) • ${dtype}`;
  prev.style.color = dtype==='mingguan' ? '#2563eb' : '#059669';
}

function saveLocal(){ localStorage.setItem(STORAGE_KEY, JSON.stringify(data)); }

// ---------- API helpers ----------
async function apiFetch(path, opts={}){
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {headers:{'Content-Type':'application/json'}, ...opts});
  if(!res.ok){
    const txt = await res.text();
    throw new Error(txt || res.statusText);
  }
  return res.json();
}

async function loadData(){
  if(!USE_API){
    data = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null') || defaultData;
    return;
  }
  try{
    const params = new URLSearchParams();
    if(pelangganFilter) params.set('search', pelangganFilter);
    // statusFilter handled in renderKanban fetch separation? simplified: fetch all then filter front
    const q = params.toString() ? `?${params}` : '';
    const rows = await apiFetch(`/services${q}`);
    data = rows.map(normalize);
    // simpan cache lokal juga
    saveLocal();
    // update indicator online
    const el = document.querySelector('.store-info span:first-child');
    if(el) el.textContent = '● Sistem Online (API)';
    if(el) el.style.color = '#10b981';
  }catch(e){
    console.warn('API gagal, fallback localStorage:', e.message);
    USE_API = false;
    data = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null') || defaultData;
    const el = document.querySelector('.store-info span:first-child');
    if(el) { el.textContent = '● Offline (localStorage)'; el.style.color = '#f59e0b'; }
    showToast('API offline - pakai data lokal');
  }
}

async function apiCreateService(payload){
  if(!USE_API){
    const newId='INV-2026-'+String(100+data.length+1).padStart(4,'0');
    const obj={id:newId, invoice:newId, ...payload, status:'Antri', date:new Date().toISOString().slice(0,10)};
    data.unshift(obj); saveLocal(); return obj;
  }
  try{
    const created = await apiFetch('/services', {method:'POST', body: JSON.stringify(payload)});
    return normalize(created);
  }catch(e){
    showToast('Gagal simpan ke API: '+ e.message);
    throw e;
  }
}

async function apiUpdateStatus(invoice, newStatus){
  if(!USE_API){
    const item=data.find(d=>d.id===invoice);
    if(item){ item.status=newStatus; saveLocal(); }
    return;
  }
  try{
    await apiFetch(`/services/${invoice}/status?status=${encodeURIComponent(newStatus)}`, {method:'PUT'});
  }catch(e){
    showToast('Gagal update status: '+ e.message);
    throw e;
  }
}

// ---------- App state ----------
let selectedKelengkapan = new Set();
let pelangganFilter = '';
let statusFilter = 'all';
let deadlineFilter = 'all'; // all, overdue, today, harian, mingguan
const PROSES_STATUSES = ['Antri','Dikerjakan','Menunggu Sparepart']; // hanya 3 status yang tampil di tab Proses Service

function setDeadlineFilter(v){
  deadlineFilter = v;
  document.querySelectorAll('[data-deadline]').forEach(b=>{
    b.classList.toggle('active', b.dataset.deadline===v);
  });
  renderKanban();
  renderSemuaService();
}
function deadlineBadge(d){
  const sisa = d.sisa_hari;
  const dl = d.deadline || '-';
  const typeLabel = d.deadline_type==='mingguan' ? '7h' : '3h';
  let cls='meta-pill';
  let txt='';
  if(d.is_overdue){
    cls='meta-pill" style="background:#fef2f2;color:#dc2626;border-color:#fecaca;font-weight:700';
    txt=`⚠ Overdue ${Math.abs(sisa)}h • ${dl} (${typeLabel})`;
  } else if(sisa===0){
    cls='meta-pill" style="background:#fffbeb;color:#b45309;border-color:#fde68a;font-weight:700';
    txt=`⏰ Hari ini • ${dl} (${typeLabel})`;
  } else if(sisa!==null){
    const color = sisa<=1 ? '#b45309' : '#374151';
    const bg = sisa<=1 ? '#fffbeb' : '#f9fafb';
    cls=`meta-pill" style="background:${bg};color:${color};border-color:#ececec`;
    txt=`⏳ ${sisa} hari lagi • ${dl} (${typeLabel})`;
  } else {
    txt=`${dl} (${typeLabel})`;
  }
  return `<span class="${cls}">${txt}</span>`;
}

// Logout handler
function handleLogout(){
  if(confirm('Yakin mau logout?')){
    localStorage.removeItem('access_token');
    localStorage.removeItem('username');
    localStorage.removeItem('role');
    showToast('Logout berhasil - mengalihkan...');
    setTimeout(()=> location.href='login.html', 600);
  }
}
function updateSidebarUser(){
  const u = localStorage.getItem('username') || 'Admin Toko';
  const r = localStorage.getItem('role') || '';
  const elU = document.getElementById('sidebar-username');
  const elR = document.getElementById('sidebar-role');
  if(elU) elU.textContent = u;
  if(elR) {
    if(r === 'superadmin') elR.textContent = 'Superadmin • Full Access';
    else if(r) elR.textContent = r;
    else elR.textContent = 'Belum login';
  }
  // tampilkan menu superadmin hanya untuk superadmin
  const isSuper = r === 'superadmin';
  const cat = document.getElementById('cat-superadmin');
  const menu = document.getElementById('menu-approval');
  if(cat) cat.style.display = isSuper ? 'block' : 'none';
  if(menu) menu.style.display = isSuper ? 'flex' : 'none';
  // selalu coba refresh badge jika superadmin
  if(isSuper) refreshPendingBadge();
  else {
    // sembunyikan semua notifikasi jika bukan superadmin
    const b = document.getElementById('badge-pending'); if(b){ b.style.display='none'; b.classList.remove('badge-pulse'); }
    const bell = document.getElementById('notifBell'); if(bell) bell.classList.remove('has-notif');
    const banner = document.getElementById('approvalBanner'); if(banner) banner.style.display='none';
  }
}

function getAuthHeaders(){
  const token = localStorage.getItem('access_token');
  const h = {'Content-Type':'application/json'};
  if(token) h['Authorization'] = `Bearer ${token}`;
  return h;
}

let lastPendingCount = -1;
async function refreshPendingBadge(){
  const badge = document.getElementById('badge-pending');
  const bell = document.getElementById('notifBell');
  const bellCount = document.getElementById('notifCount');
  const banner = document.getElementById('approvalBanner');
  const bannerTitle = document.getElementById('bannerTitle');
  const bannerSub = document.getElementById('bannerSub');
  const role = localStorage.getItem('role');
  const token = localStorage.getItem('access_token');

  // jika bukan superadmin atau belum login → sembunyikan
  if(role !== 'superadmin' || !token){
    if(badge){ badge.style.display='none'; badge.classList.remove('badge-pulse'); }
    if(bell) bell.classList.remove('has-notif');
    if(banner) banner.style.display='none';
    return;
  }
  try{
    const res = await fetch(`${API_BASE}/auth/pending`, {headers: getAuthHeaders()});
    if(!res.ok){
      const txt = await res.text();
      console.warn('refreshPendingBadge failed', res.status, txt);
      throw new Error(txt || 'no auth');
    }
    const rows = await res.json();
    const n = Array.isArray(rows) ? rows.length : 0;

    // sidebar badge
    if(badge){
      badge.textContent = n;
      badge.style.display = n > 0 ? 'inline-block' : 'none';
      if(n > 0) badge.classList.add('badge-pulse');
      else badge.classList.remove('badge-pulse');
      badge.style.background = n > 0 ? '#f59e0b' : '#2a2c2f';
    }
    // topbar bell
    if(bell){
      if(n > 0) bell.classList.add('has-notif');
      else bell.classList.remove('has-notif');
    }
    if(bellCount) bellCount.textContent = n;

    // dashboard banner
    if(banner){
      if(n > 0){
        banner.style.display = 'flex';
        if(bannerTitle) bannerTitle.textContent = `${n} akun menunggu persetujuan superadmin`;
        if(bannerSub) bannerSub.textContent = `Admin/teknisi baru menunggu diizinkan • klik untuk buka Persetujuan Akun`;
        banner.style.cursor = 'pointer';
      } else {
        banner.style.display = 'none';
      }
    }

    // toast hanya sekali saat count naik / pertama kali >0
    if(n > 0 && n !== lastPendingCount){
      // jangan spam jika baru load pertama dan 0→n, tapi beri notifikasi jelas
      if(lastPendingCount !== -1 || n > 0){
        showToast(`🔔 Ada ${n} akun menunggu persetujuan — buka Persetujuan Akun`);
      }
      // juga fallback: jika user tidak di dashboard, tetap beri petunjuk via banner
    }
    lastPendingCount = n;
    console.log('[notif] pending:', n);
  }catch(e){
    console.warn('refreshPendingBadge error:', e.message);
    // jangan sembunyikan total jika error sementara, biar user tau offline
    // tapi jika 401 (token expired) sembunyikan dan arahkan login
    if(String(e.message).includes('401') || String(e.message).includes('Token')){
      if(badge) badge.style.display='none';
      if(bell) bell.classList.remove('has-notif');
    }
  }
}

function handleNotifClick(){
  const role = localStorage.getItem('role');
  if(role !== 'superadmin'){
    showToast('⛔ Hanya superadmin yang bisa menyetujui akun');
    return;
  }
  // jika ada pending, langsung ke approval, jika tidak tetap buka approval
  switchView('approval-akun');
}

// ---------- Superadmin Approval ----------
let approvalCache = [];
let allUsersCache = [];
async function loadApprovalData(){
  const tbody = document.getElementById('tbodyApproval');
  const countEl = document.getElementById('approvalCount');
  const allCount = document.getElementById('allUsersCount');
  if(localStorage.getItem('role') !== 'superadmin'){
    if(tbody) tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:24px;color:#dc2626">⛔ Hanya superadmin yang bisa melihat halaman ini. Login sebagai superadmin / bismillah</td></tr>`;
    const at = document.getElementById('tbodyAllUsers');
    if(at) at.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:16px;color:#dc2626">⛔ Hanya superadmin</td></tr>`;
    return;
  }
  const token = localStorage.getItem('access_token');
  if(!token){
    if(tbody) tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:24px;color:#dc2626">Belum login — <a href="login.html">login dulu</a></td></tr>`;
    return;
  }
  if(tbody) tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:24px;color:#8a8f98">Memuat pending...</td></tr>`;
  try{
    const res = await fetch(`${API_BASE}/auth/pending`, {headers: getAuthHeaders()});
    if(!res.ok){ const t=await res.text(); throw new Error(t); }
    const pending = await res.json();
    approvalCache = pending;
    if(countEl) countEl.textContent = pending.length + ' menunggu';
    refreshPendingBadge();
    if(!pending.length){
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:24px;color:#059669">✅ Tidak ada akun menunggu persetujuan</td></tr>`;
    } else {
      tbody.innerHTML = pending.map((u,i)=>`
        <tr>
          <td>${i+1}</td>
          <td><strong>${escapeHtml(u.username)}</strong></td>
          <td><span class="badge-status ${u.role==='admin'?'Dikerjakan':u.role==='teknisi'?'Selesai':'Antri'}" style="text-transform:capitalize">${escapeHtml(u.role)}</span></td>
          <td><span style="background:#fef2f2;color:#dc2626;padding:4px 8px;border-radius:20px;font-size:11px">Menunggu</span></td>
          <td style="font-size:12px;color:#6b7280">${u.created_at ? new Date(u.created_at).toLocaleString('id-ID') : '-'}</td>
          <td style="text-align:center;display:flex;gap:6px;justify-content:center;flex-wrap:wrap">
            <button class="btn btn-dark small" style="padding:6px 10px;font-size:11px" onclick="approveUser(${u.id})">✓ Setujui</button>
            <button class="btn btn-ghost small" style="padding:6px 10px;font-size:11px" onclick="openEditUserModal(${u.id})">✎ Edit</button>
            <button class="btn btn-ghost small" style="padding:6px 10px;font-size:11px;color:#dc2626;border-color:#fecaca" onclick="rejectUser(${u.id}, '${escapeHtml(u.username)}')">✕ Tolak</button>
          </td>
        </tr>
      `).join('');
    }
    // also load all users
    try{
      const res2 = await fetch(`${API_BASE}/auth/users`, {headers: getAuthHeaders()});
      if(res2.ok){
        const all = await res2.json();
        allUsersCache = all;
        if(allCount) allCount.textContent = all.length + ' user';
        renderAllUsers();
      }
    }catch{}
  }catch(e){
    if(tbody) tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:24px;color:#dc2626">Gagal: ${escapeHtml(e.message).slice(0,300)}</td></tr>`;
  }
}

function renderAllUsers(){
  const tbody = document.getElementById('tbodyAllUsers');
  if(!tbody) return;
  const q = (document.getElementById('searchUser')?.value || '').toLowerCase();
  const fRole = document.getElementById('filterRoleUser')?.value || '';
  const fStatus = document.getElementById('filterStatusUser')?.value || '';
  let filtered = [...allUsersCache];
  if(q) filtered = filtered.filter(u => u.username.toLowerCase().includes(q) || u.role.toLowerCase().includes(q));
  if(fRole) filtered = filtered.filter(u => u.role === fRole);
  if(fStatus === 'aktif') filtered = filtered.filter(u => u.is_active);
  if(fStatus === 'beku') filtered = filtered.filter(u => !u.is_active);
  // sort: superadmin first, then aktif, then nama
  filtered.sort((a,b)=> (a.role==='superadmin'?-1:b.role==='superadmin'?1:0) || (b.is_active - a.is_active));
  const me = localStorage.getItem('username');
  if(!filtered.length){
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:18px;color:#8a8f98">Tidak ada user sesuai filter</td></tr>`;
    return;
  }
  tbody.innerHTML = filtered.map(u=>{
    const isMe = u.username === me;
    const isSuper = u.role === 'superadmin';
    const statusBadge = u.is_active
      ? '<span style="background:#ecfdf5;color:#059669;padding:4px 8px;border-radius:20px;font-size:11px">Aktif</span>'
      : '<span style="background:#fef2f2;color:#dc2626;padding:4px 8px;border-radius:20px;font-size:11px">Beku</span>';
    const freezeLabel = u.is_active ? '❄ Bekukan' : '✓ Aktifkan';
    const freezeStyle = u.is_active ? 'color:#b45309;border-color:#fde68a;background:#fffbeb' : 'color:#059669;border-color:#a7f3d0;background:#ecfdf5';
    const disAttr = (isSuper || isMe) ? 'disabled style="opacity:.45;cursor:not-allowed"' : '';
    return `
      <tr style="${!u.is_active?'background:#fffbeb':''}">
        <td><strong>${escapeHtml(u.username)}</strong>${isMe?' <span style="font-size:10px;background:#111;color:#fff;padding:2px 6px;border-radius:8px">Anda</span>':''}</td>
        <td><span class="badge-status ${u.role==='superadmin'?'Service Failed':u.role==='admin'?'Dikerjakan':u.role==='teknisi'?'Selesai':'Antri'}" style="text-transform:capitalize;font-size:11px">${escapeHtml(u.role)}</span></td>
        <td>${statusBadge}</td>
        <td style="font-size:11px;color:#6b7280">${u.created_at ? new Date(u.created_at).toLocaleDateString('id-ID') : '-'}</td>
        <td style="font-size:11px;color:#6b7280">${u.last_login ? new Date(u.last_login).toLocaleString('id-ID') : '-'}</td>
        <td style="text-align:center">
          <div style="display:flex;gap:6px;justify-content:center;flex-wrap:wrap">
            <button class="btn btn-ghost small" style="padding:5px 9px;font-size:11px" onclick="openEditUserModal(${u.id})" ${isSuper && u.username!=='superadmin' ? '' : isSuper?'disabled style="opacity:.45;cursor:not-allowed"':''}>✎ Edit</button>
            <button class="btn btn-ghost small" style="padding:5px 9px;font-size:11px;${freezeStyle}" onclick="toggleFreezeUser(${u.id})" ${disAttr}>${freezeLabel}</button>
            <button class="btn btn-ghost small" style="padding:5px 9px;font-size:11px;color:#dc2626;border-color:#fecaca" onclick="deleteUser(${u.id}, '${escapeHtml(u.username)}')" ${disAttr}>🗑 Hapus</button>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

function filterAllUsers(){ renderAllUsers(); }

function openEditUserModal(userId){
  const u = allUsersCache.find(x=>x.id===userId) || approvalCache.find(x=>x.id===userId);
  if(!u) return showToast('User tidak ditemukan');
  document.getElementById('editUserId').value = u.id;
  document.getElementById('editUsername').value = u.username;
  document.getElementById('editRole').value = u.role;
  document.getElementById('editPassword').value = '';
  document.getElementById('editUserSub').textContent = `Edit ${u.username} • ${u.role} • ${u.is_active?'Aktif':'Beku'}`;
  document.getElementById('userEditModal').classList.add('show');
}
function closeUserModal(){ document.getElementById('userEditModal').classList.remove('show'); }

async function submitUserEdit(e){
  e.preventDefault();
  const id = parseInt(document.getElementById('editUserId').value);
  const username = document.getElementById('editUsername').value.trim();
  const role = document.getElementById('editRole').value;
  const password = document.getElementById('editPassword').value;
  const payload = { username, role };
  if(password) payload.password = password;
  try{
    const res = await fetch(`${API_BASE}/auth/users/${id}`, {method:'PUT', headers: getAuthHeaders(), body: JSON.stringify(payload)});
    const j = await res.json();
    if(!res.ok) throw new Error(j.detail || 'Gagal edit');
    showToast(`✎ ${j.username} diperbarui`);
    closeUserModal();
    await loadApprovalData();
    // jika edit diri sendiri, update sidebar
    if(j.username === localStorage.getItem('username') || j.id === allUsersCache.find(x=>x.username===localStorage.getItem('username'))?.id){
      localStorage.setItem('username', j.username);
      localStorage.setItem('role', j.role);
      updateSidebarUser();
    }
  }catch(err){ showToast('Gagal edit: '+err.message); }
}

async function toggleFreezeUser(userId){
  const u = allUsersCache.find(x=>x.id===userId);
  const action = u && u.is_active ? 'bekukan (nonaktifkan login)' : 'aktifkan kembali';
  if(!confirm(`Yakin ingin ${action} akun "${u?u.username:userId}"?`)) return;
  try{
    const res = await fetch(`${API_BASE}/auth/toggle/${userId}`, {method:'POST', headers: getAuthHeaders()});
    const j = await res.json();
    if(!res.ok) throw new Error(j.detail || 'Gagal');
    showToast(j.is_active ? `✓ ${j.username} diaktifkan` : `❄ ${j.username} dibekukan`);
    await loadApprovalData();
  }catch(e){ showToast('Gagal: '+e.message); }
}

async function deleteUser(userId, username){
  if(!confirm(`Hapus akun "${username}"? Tidak bisa dibatalkan. User harus register ulang.`)) return;
  try{
    const res = await fetch(`${API_BASE}/auth/users/${userId}`, {method:'DELETE', headers: getAuthHeaders()});
    const j = await res.json();
    if(!res.ok) throw new Error(j.detail || 'Gagal hapus');
    showToast(`🗑 ${username} dihapus`);
    await loadApprovalData();
  }catch(e){ showToast('Gagal hapus: '+e.message); }
}

async function approveUser(userId){
  if(!confirm('Setujui akun ini? Akun akan bisa login.')) return;
  try{
    const res = await fetch(`${API_BASE}/auth/approve/${userId}`, {method:'POST', headers: getAuthHeaders()});
    const j = await res.json();
    if(!res.ok) throw new Error(j.detail || 'Gagal approve');
    showToast(`✅ ${j.username} disetujui — sekarang bisa login`);
    await loadApprovalData();
  }catch(e){ showToast('Gagal approve: '+e.message); }
}

async function rejectUser(userId, username){
  if(!confirm(`Tolak & hapus akun "${username}"? Tidak bisa dibatalkan.`)) return;
  try{
    const res = await fetch(`${API_BASE}/auth/reject/${userId}`, {method:'POST', headers: getAuthHeaders()});
    const j = await res.json();
    if(!res.ok) throw new Error(j.detail || 'Gagal tolak');
    showToast(`🗑️ ${username} ditolak & dihapus`);
    await loadApprovalData();
  }catch(e){ showToast('Gagal tolak: '+e.message); }
}

// Init
document.addEventListener('DOMContentLoaded', async ()=>{
  updateSidebarUser();
  // guard: jika belum login, redirect ke login (optional - aktifkan jika mau proteksi)
  // if(!localStorage.getItem('access_token')){ location.href='login.html'; return; }
  setupNavigation();
  setupChips();
  await loadData();
  renderAll();
  updateInvoicePreview();
  // listeners
  const gs = document.getElementById('globalSearch');
  if(gs) gs.addEventListener('input', e=>{
    const q=e.target.value.toLowerCase();
    pelangganFilter = q;
    statusFilter = 'all';
    switchView('pelanggan');
    const sp = document.getElementById('searchPelanggan');
    if(sp) sp.value = q;
    // jika pakai API, reload
    if(USE_API){ loadData().then(renderPelanggan); } else renderPelanggan();
  });
  const sp2 = document.getElementById('searchPelanggan');
  if(sp2) sp2.addEventListener('input', e=>{
    pelangganFilter=e.target.value.toLowerCase();
    if(USE_API){ loadData().then(renderPelanggan); } else renderPelanggan();
  });
  const fd = document.getElementById('filterDevice');
  if(fd) fd.addEventListener('change', ()=>{
    if(USE_API){ loadData().then(renderPelanggan); } else renderPelanggan();
  });
  const ham = document.getElementById('hamburger');
  const overlay = document.getElementById('sidebarOverlay');
  function openSidebar(){ const sb=document.getElementById('sidebar'); if(sb){ sb.classList.add('open'); if(overlay) overlay.classList.add('show'); document.body.style.overflow='hidden'; } }
  function closeSidebar(){ const sb=document.getElementById('sidebar'); if(sb){ sb.classList.remove('open'); if(overlay) overlay.classList.remove('show'); document.body.style.overflow=''; } }
  window.closeSidebar=closeSidebar;
  if(ham) ham.addEventListener('click', ()=>{
    const sb=document.getElementById('sidebar');
    if(sb.classList.contains('open')) closeSidebar(); else openSidebar();
  });
  if(overlay) overlay.addEventListener('click', closeSidebar);
  // auto close sidebar on menu click (mobile)
  document.querySelectorAll('.menu-item').forEach(m=>m.addEventListener('click', ()=>{ if(window.innerWidth<=860) closeSidebar(); }));
  document.querySelectorAll('.tab[data-filter]').forEach(t=>t.addEventListener('click', ()=>{
    document.querySelectorAll('.tab[data-filter]').forEach(x=>x.classList.remove('active'));
    t.classList.add('active');
    statusFilter=t.dataset.filter; renderKanban();
  }));
  const ss=document.getElementById('searchSemua'); if(ss) ss.addEventListener('input', renderSemuaService);
  const fs=document.getElementById('filterStatusSemua'); if(fs) fs.addEventListener('change', renderSemuaService);
  // swipe to close sidebar on mobile
  let touchStartX=0;
  document.addEventListener('touchstart', e=>{ touchStartX=e.touches[0].clientX; }, {passive:true});
  document.addEventListener('touchend', e=>{
    const diff=e.changedTouches[0].clientX - touchStartX;
    const sb=document.getElementById('sidebar');
    if(sb && sb.classList.contains('open') && diff < -50) closeSidebar();
    if(sb && !sb.classList.contains('open') && touchStartX<20 && diff>50) openSidebar();
  }, {passive:true});
  // cek health
  checkHealth();
  updateDeadlinePreview();
  // polling notifikasi pending — selalu jalan, di dalam fungsi sudah cek role
  refreshPendingBadge(); // langsung cek saat load
  setInterval(refreshPendingBadge, 12000);
  // juga cek lagi setelah 1 detik (tunggu token settle)
  setTimeout(refreshPendingBadge, 1000);
});

async function checkHealth(){
  try{
    const res = await fetch(API_BASE.replace('/api','') + '/health');
    if(res.ok){
      const j = await res.json();
      console.log('Health:', j);
    }
  }catch{}
}

function setupNavigation(){
  document.querySelectorAll('.menu-item').forEach(btn=>{
    btn.addEventListener('click', ()=> switchView(btn.dataset.view));
  });
}
function switchView(view){
  document.querySelectorAll('.menu-item').forEach(b=>b.classList.toggle('active', b.dataset.view===view));
  document.querySelectorAll('.view').forEach(v=>v.classList.remove('active'));
  const el=document.getElementById('view-'+view);
  if(el) el.classList.add('active');
  const titles={
    dashboard:['Dashboard Overview','Ringkasan service hari ini — Selasa, 2 September 2026'],
    'semua-service':['Semua Service','Daftar lengkap semua service — filter & cari'],
    'service-masuk':['Service Masuk','Input device baru & kelola antrian masuk'],
    pelanggan:['Data Pelanggan','Kelola pelanggan loyal & riwayat service'],
    'tambah-pelanggan':['Tambah Pelanggan','Tambah data pelanggan baru'],
    proses:['Proses Service','Hanya Antri • Dikerjakan • Menunggu Sparepart (status lain ada di menu masing-masing)'],
    'bisa-diambil':['Bisa Diambil','Device Selesai & siap diambil pelanggan (status Selesai otomatis masuk sini)'],
    'sudah-diambil':['Sudah Diambil','Riwayat device yang sudah diambil'],
    'service-failed':['Service Failed','Gagal diperbaiki — perlu follow-up'],
    'status-garansi':['Status Garansi','Service dalam masa garansi'],
    'inventory-sparepart':['Sparepart','Kelola stok sparepart'],
    'inventory-stok':['Stok','Ringkasan stok inventory'],
    'inventory-alat':['Alat','Peralatan teknisi'],
    'inventory-tambah':['Tambah Item','Tambah item inventory baru'],
    'transaksi-penjualan':['Penjualan','Riwayat transaksi penjualan'],
    'transaksi-pembayaran':['Pembayaran','Metode & status pembayaran'],
    'laporan-service':['Laporan Service','Rekap service per periode'],
    'laporan-teknisi':['Laporan Teknisi','Performa teknisi'],
    'laporan-penjualan':['Laporan Penjualan','Pendapatan & penjualan'],
    'approval-akun':['Persetujuan Akun','Kelola persetujuan admin & teknisi — superadmin only']
  };
  if(titles[view]){
    document.getElementById('page-title').textContent=titles[view][0];
    document.getElementById('page-subtitle').textContent=titles[view][1];
  }
  if(window.innerWidth<=860) closeSidebar();
  else document.getElementById('sidebar').classList.remove('open');
  if(view==='dashboard') renderDashboard();
  if(view==='proses') renderKanban();
  if(view==='semua-service') renderSemuaService();
  if(view==='bisa-diambil') renderStatusView('kanbanBisaDiambil','Bisa Diambil');
  if(view==='sudah-diambil') renderStatusView('kanbanSudahDiambil','Sudah Diambil');
  if(view==='service-failed') renderStatusView('kanbanFailed','Service Failed');
  if(view==='status-garansi') renderStatusView('kanbanGaransi','Garansi');
  if(view==='approval-akun') loadApprovalData();
}

function setupChips(){
  document.querySelectorAll('.chip').forEach(c=>{
    c.addEventListener('click', ()=>{
      c.classList.toggle('active');
      const v=c.dataset.value;
      if(selectedKelengkapan.has(v)) selectedKelengkapan.delete(v); else selectedKelengkapan.add(v);
    });
  });
}

function renderAll(){
  renderDashboard(); renderQueue(); renderPelanggan(); renderKanban(); updateStats();
}

function escapeHtml(s){
  return String(s).replace(/[&<>"']/g, m=>({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[m]));
}

function updateStats(){
  document.getElementById('stat-masuk').textContent = data.length;
  document.getElementById('stat-proses').textContent = data.filter(d=>['Antri','Dikerjakan','Menunggu Sparepart'].includes(d.status)).length;
  document.getElementById('stat-selesai').textContent = data.filter(d=>d.status==='Selesai').length;
  document.getElementById('queueCount').textContent = data.length+' antrian';
  const badge = document.querySelector('.menu-item[data-view="service-masuk"] .badge');
  if(badge) badge.textContent = data.length;
  // deadline counts (client fallback)
  const overdueCount = data.filter(d=>d.is_overdue).length;
  const todayDl = data.filter(d=>d.deadline===new Date().toISOString().slice(0,10) && !['Selesai','Sudah Diambil','Dibatalkan'].includes(d.status)).length;
  const hCount = data.filter(d=>d.deadline_type==='harian').length;
  const mCount = data.filter(d=>d.deadline_type==='mingguan').length;
  const elO = document.getElementById('stat-overdue'); if(elO) elO.textContent = overdueCount;
  const elT = document.getElementById('stat-deadline-today'); if(elT) elT.textContent = todayDl;
  const elH = document.getElementById('stat-harian'); if(elH) elH.textContent = hCount;
  const elM = document.getElementById('stat-mingguan'); if(elM) elM.textContent = mCount;
  const cO = document.getElementById('countOverdue'); if(cO) cO.textContent = overdueCount;
  const cT = document.getElementById('countToday'); if(cT) cT.textContent = todayDl;
  const cH = document.getElementById('countHarian'); if(cH) cH.textContent = hCount;
  const cM = document.getElementById('countMingguan'); if(cM) cM.textContent = mCount;
  // jika API online, fetch stats real
  if(USE_API){
    apiFetch('/stats').then(s=>{
      document.getElementById('stat-masuk').textContent = s.total_masuk;
      document.getElementById('stat-proses').textContent = s.dalam_proses;
      document.getElementById('stat-selesai').textContent = s.selesai_hari_ini;
      const el = document.querySelector('.stat-card.dark h3');
      if(el) el.textContent = 'Rp ' + Number(s.estimasi_pendapatan).toLocaleString('id-ID');
      if(elO) elO.textContent = s.overdue ?? overdueCount;
      if(elT) elT.textContent = s.deadline_hari_ini ?? todayDl;
      if(elH) elH.textContent = s.harian ?? hCount;
      if(elM) elM.textContent = s.mingguan ?? mCount;
      if(cO) cO.textContent = s.overdue ?? overdueCount;
      if(cT) cT.textContent = s.deadline_hari_ini ?? todayDl;
      if(cH) cH.textContent = s.harian ?? hCount;
      if(cM) cM.textContent = s.mingguan ?? mCount;
    }).catch(()=>{});
  }
}

function renderDashboard(){
  const tbody=document.querySelector('#tableDashboard tbody');
  if(!tbody) return;
  tbody.innerHTML = data.slice(0,4).map(d=>`
    <tr>
      <td><strong>${escapeHtml(d.id)}</strong><br><span style="color:#8a8f98;font-size:11px">${escapeHtml(d.date)}</span></td>
      <td><div class="avatar-cell"><img src="https://i.pravatar.cc/100?u=${escapeHtml(d.wa)}"><div><strong>${escapeHtml(d.nama)}</strong><br><span style="color:#8a8f98">${escapeHtml(d.device)}</span></div></div></td>
      <td>${escapeHtml(d.keluhan)}</td>
      <td><span class="badge-status ${escapeHtml(d.status)}">${escapeHtml(d.status)}</span></td>
    </tr>
  `).join('');
}

function renderQueue(){
  const wrap=document.getElementById('queueList');
  if(!wrap) return;
  wrap.innerHTML = data.slice(0,6).map(d=>`
    <div class="queue-item">
      <img src="https://i.pravatar.cc/100?u=${escapeHtml(d.wa)}">
      <div><strong>${escapeHtml(d.nama)}</strong><br><span>${escapeHtml(d.device)} • ${escapeHtml(d.id)}</span></div>
      <span class="price">Rp ${Number(d.biaya).toLocaleString('id-ID')}</span>
    </div>
  `).join('');
}

function renderPelanggan(){
  const tbody=document.querySelector('#tablePelanggan tbody');
  if(!tbody) return;
  const filterDevice=document.getElementById('filterDevice').value;
  let filtered=[...data];
  if(pelangganFilter) filtered=filtered.filter(d=> (d.nama+d.device+d.wa+d.id).toLowerCase().includes(pelangganFilter));
  if(filterDevice) filtered=filtered.filter(d=>d.device.includes(filterDevice));
  tbody.innerHTML = filtered.map(d=>`
    <tr>
      <td><div class="avatar-cell"><img src="https://i.pravatar.cc/100?u=${escapeHtml(d.wa)}"><div><strong>${escapeHtml(d.nama)}</strong><br><span style="color:#8a8f98;font-size:12px">${escapeHtml(d.wa)}</span></div></div></td>
      <td>${escapeHtml(d.device)}</td>
      <td><span style="background:#f3f4f6;padding:4px 8px;border-radius:20px;font-size:12px">1x</span></td>
      <td>${escapeHtml(d.date)}</td>
      <td><span class="badge-status Selesai">Member</span></td>
      <td><button class="btn btn-ghost small" onclick="openDetail('${escapeHtml(d.id)}')">Detail</button></td>
    </tr>
  `).join('') || `<tr><td colspan="6" style="text-align:center;padding:20px;color:#8a8f98">Tidak ada data</td></tr>`;
  const pc = document.getElementById('pelangganCount');
  if(pc) pc.textContent = filtered.length + ' pelanggan';
  const pi = document.getElementById('paginationInfo');
  if(pi) pi.textContent = `Menampilkan ${filtered.length} dari ${data.length}`;
}

function statusOptions(){
  return ['Antri','Dikerjakan','Menunggu Sparepart','Selesai','Bisa Diambil','Sudah Diambil','Service Failed','Garansi','Dibatalkan'];
}
function passesDeadlineFilter(d){
  if(deadlineFilter==='all') return true;
  if(deadlineFilter==='overdue') return d.is_overdue;
  if(deadlineFilter==='today') return d.deadline===new Date().toISOString().slice(0,10);
  if(deadlineFilter==='harian') return d.deadline_type==='harian';
  if(deadlineFilter==='mingguan') return d.deadline_type==='mingguan';
  return true;
}
function renderKanban(){
  const wrap=document.getElementById('kanban');
  if(!wrap) return;
  // Guard: jika filter lama masih 'Selesai' (dari cache), paksa ke 'all'
  if(statusFilter!=='all' && !PROSES_STATUSES.includes(statusFilter)){
    statusFilter='all';
    document.querySelectorAll('#view-proses .tab[data-filter]').forEach(b=> b.classList.toggle('active', b.dataset.filter==='all'));
  }
  // Basis: hanya 3 status yang boleh tampil di tab Proses Service
  let filtered = data.filter(d=> PROSES_STATUSES.includes(d.status));
  if(statusFilter!=='all') filtered=filtered.filter(d=>d.status===statusFilter);
  if(pelangganFilter){
     filtered=filtered.filter(d=> (d.nama+d.device+d.keluhan).toLowerCase().includes(pelangganFilter));
  }
  filtered = filtered.filter(passesDeadlineFilter);
  const opts = statusOptions().map(s=>`<option>${s}</option>`).join('');
  wrap.innerHTML = filtered.map(d=>`
    <div class="service-card" style="${d.is_overdue?'border-color:#fecaca;background:#fffafa':d.sisa_hari===0?'border-color:#fde68a':''}">
      <div class="service-card-head">
        <div><h4>${escapeHtml(d.device)}</h4><p>${escapeHtml(d.id)} • ${escapeHtml(d.nama)}</p></div>
        <span class="badge-status ${escapeHtml(d.status)}">${escapeHtml(d.status)}</span>
      </div>
      <p>📝 ${escapeHtml(d.keluhan)}</p>
      <div class="service-meta">
        <span class="meta-pill">👨‍🔧 ${escapeHtml(d.teknisi)}</span>
        <span class="meta-pill">💰 Rp ${Number(d.biaya).toLocaleString('id-ID')}</span>
        <span class="meta-pill">📦 ${escapeHtml((d.kelengkapan||[]).join(', '))}</span>
        ${deadlineBadge(d)}
      </div>
      <div class="card-actions">
        <select onchange="updateStatus('${escapeHtml(d.id)}', this.value)" style="flex:1;padding:8px;border-radius:10px;border:1px solid #ececec;font-size:12px">
          <option disabled selected>Ubah status</option>
          ${opts}
        </select>
        <button class="btn btn-ghost small" onclick="openDetail('${escapeHtml(d.id)}')">Detail</button>
      </div>
    </div>
  `).join('') || `<div style="grid-column:1/-1;text-align:center;padding:40px;color:#8a8f98">Tidak ada service dengan status Antri / Dikerjakan / Menunggu Sparepart</div>`;
  // update hitungan tab hanya untuk tab filter di view-proses
  document.querySelectorAll('#view-proses .tab[data-filter]').forEach(tab=>{
    const f=tab.dataset.filter;
    const count = f==='all'? data.filter(d=> PROSES_STATUSES.includes(d.status)).length : data.filter(d=>d.status===f).length;
    const sp = tab.querySelector('span');
    if(sp) sp.textContent = count;
  });
}
function renderSemuaService(){
  const tbody=document.querySelector('#tableSemua tbody');
  if(!tbody) return;
  const q = (document.getElementById('searchSemua')?.value || '').toLowerCase();
  const f = document.getElementById('filterStatusSemua')?.value || '';
  let filtered=[...data];
  if(q) filtered=filtered.filter(d=> (d.id+d.nama+d.device+d.wa+d.keluhan).toLowerCase().includes(q));
  if(f) filtered=filtered.filter(d=>d.status===f);
  filtered = filtered.filter(passesDeadlineFilter);
  tbody.innerHTML = filtered.map(d=>`
    <tr style="${d.is_overdue?'background:#fffafa':''}">
      <td><strong>${escapeHtml(d.id)}</strong><br><span style="color:#8a8f98;font-size:11px">${escapeHtml(d.date)} • ${deadlineBadge(d).replace(/<[^>]*>/g,'')}</span></td>
      <td><div class="avatar-cell"><img src="https://i.pravatar.cc/100?u=${escapeHtml(d.wa)}"><div><strong>${escapeHtml(d.nama)}</strong><br><span style="color:#8a8f98">${escapeHtml(d.device)}</span></div></div></td>
      <td>${escapeHtml(d.keluhan)}<br><span style="font-size:11px">${deadlineBadge(d)}</span></td>
      <td>${escapeHtml(d.teknisi)}</td>
      <td>Rp ${Number(d.biaya).toLocaleString('id-ID')}</td>
      <td><span class="badge-status ${escapeHtml(d.status)}">${escapeHtml(d.status)}</span></td>
      <td><button class="btn btn-ghost small" onclick="openDetail('${escapeHtml(d.id)}')">Detail</button></td>
    </tr>
  `).join('') || `<tr><td colspan="7" style="text-align:center;padding:20px;color:#8a8f98">Tidak ada data</td></tr>`;
  const el=document.getElementById('semuaCount'); if(el) el.textContent = filtered.length + ' service';
}
function renderStatusView(targetId, statusName){
  const wrap=document.getElementById(targetId);
  if(!wrap) return;
  // Jika tab Bisa Diambil, tampilkan status 'Selesai' + 'Bisa Diambil' (sesuai request)
  let filtered;
  if(statusName==='Bisa Diambil'){
    filtered = data.filter(d=> ['Bisa Diambil','Selesai'].includes(d.status)).filter(passesDeadlineFilter);
  } else {
    filtered = data.filter(d=>d.status===statusName).filter(passesDeadlineFilter);
  }
  const opts = statusOptions().map(s=>`<option>${s}</option>`).join('');
  wrap.innerHTML = filtered.map(d=>`
    <div class="service-card" style="${d.is_overdue?'border-color:#fecaca;background:#fffafa':''}">
      <div class="service-card-head"><div><h4>${escapeHtml(d.device)}</h4><p>${escapeHtml(d.id)} • ${escapeHtml(d.nama)}</p></div><span class="badge-status ${escapeHtml(d.status)}">${escapeHtml(d.status)}</span></div>
      <p>📝 ${escapeHtml(d.keluhan)}</p>
      <div class="service-meta"><span class="meta-pill">👨‍🔧 ${escapeHtml(d.teknisi)}</span><span class="meta-pill">💰 Rp ${Number(d.biaya).toLocaleString('id-ID')}</span>${deadlineBadge(d)}</div>
      <div class="card-actions"><select onchange="updateStatus('${escapeHtml(d.id)}', this.value)" style="flex:1;padding:8px;border-radius:10px;border:1px solid #ececec;font-size:12px"><option disabled selected>Ubah status</option>${opts}</select><button class="btn btn-ghost small" onclick="openDetail('${escapeHtml(d.id)}')">Detail</button></div>
    </div>
  `).join('') || `<div style="grid-column:1/-1;text-align:center;padding:40px;color:#8a8f98">Belum ada service dengan status <strong>${statusName==='Bisa Diambil' ? 'Selesai / Bisa Diambil' : escapeHtml(statusName)}</strong></div>`;
}
async function handleCustomerSubmit(e){
  e.preventDefault();
  const nama=document.getElementById('c-nama').value.trim();
  const wa=document.getElementById('c-wa').value.trim();
  const note=document.getElementById('c-note').value.trim();
  if(!nama||!wa) return showToast('Nama & WA wajib!');
  if(USE_API){
    try{ await apiFetch('/customers', {method:'POST', body: JSON.stringify({nama, wa})}); showToast('Pelanggan ditambahkan ✓'); e.target.reset(); await loadData(); renderPelanggan(); switchView('pelanggan'); }catch(err){ showToast('Gagal: '+err.message); }
  } else { showToast('Pelanggan ditambahkan (lokal) ✓'); e.target.reset(); switchView('pelanggan'); }
}

async function updateStatus(id, newStatus){
  try{
    await apiUpdateStatus(id, newStatus);
    const item=data.find(d=>d.id===id);
    if(item) item.status=newStatus;
    if(!USE_API) saveLocal();
    else await loadData();
    renderAll(); showToast(`Status ${id} → ${newStatus}`);
  }catch(e){
    showToast('Gagal update: '+ e.message);
  }
}
async function updateDeadline(invoice){
  const sel = document.getElementById('modalDeadlineType');
  if(!sel) return;
  const newType = sel.value;
  try{
    if(USE_API){
      await apiFetch(`/services/${invoice}`, {method:'PATCH', body: JSON.stringify({deadline_type: newType})});
      await loadData();
    } else {
      const item=data.find(d=>d.id===invoice);
      if(item){ item.deadline_type=newType; item.deadline=computeDeadline(item.date, newType); item.sisa_hari=computeSisa(item.deadline); item.is_overdue = item.sisa_hari<0 && !['Selesai','Sudah Diambil','Dibatalkan'].includes(item.status); saveLocal(); }
    }
    renderAll();
    closeModal();
    showToast(`Deadline ${invoice} → ${newType} (${newType==='harian'?'3 hari':'7 hari'})`);
  }catch(e){ showToast('Gagal ubah deadline: '+e.message); }
}

async function handleServiceSubmit(e){
  e.preventDefault();
  const nama=document.getElementById('f-nama').value.trim();
  const wa=document.getElementById('f-wa').value.trim();
  const device=document.getElementById('f-device').value.trim();
  const imei=document.getElementById('f-imei').value.trim();
  const keluhan=document.getElementById('f-keluhan').value.trim();
  const biaya=parseInt(document.getElementById('f-biaya').value)||0;
  const teknisi=document.getElementById('f-teknisi').value;
  const estimasi=document.getElementById('f-estimasi').value || null;
  if(!nama||!wa||!device||!keluhan) return showToast('Lengkapi field wajib!');

  const dlType = document.getElementById('f-deadline-type')?.value || 'harian';
  const payload = {
    nama, wa,
    device: device,
    imei: imei || null,
    keluhan,
    kelengkapan: [...selectedKelengkapan],
    biaya,
    teknisi,
    status: "Antri",
    estimasi_selesai: estimasi,
    deadline_type: dlType
  };

  try{
    const created = await apiCreateService(payload);
    // jika pakai API, reload dari server untuk dapat invoice asli
    if(USE_API) await loadData();
    else data.unshift(created);
    renderAll(); resetForm(); showToast('Service berhasil disimpan! '+(created.invoice||created.id));
    switchView('proses');
  }catch(err){
    showToast('Gagal simpan: '+ err.message);
  }
}
function resetForm(){
  document.getElementById('serviceForm').reset();
  // after reset, set default deadline harian
  const sel = document.getElementById('f-deadline-type');
  if(sel) sel.value = 'harian';
  updateDeadlinePreview();
  selectedKelengkapan.clear();
  document.querySelectorAll('.chip').forEach(c=>c.classList.remove('active'));
  updateInvoicePreview();
}
async function updateInvoicePreview(){
  const el = document.getElementById('invoicePreview');
  if(!el) return;
  if(USE_API){
    try{
      const stats = await apiFetch('/stats');
      const nextNum = 100 + stats.total_masuk + 1;
      el.textContent = `INV-${new Date().getFullYear()}-${String(nextNum).padStart(4,'0')}`;
      return;
    }catch{}
  }
  const next='INV-2026-'+String(100+data.length+1).padStart(4,'0');
  el.textContent=next;
}
function openDetail(id){
  const d=data.find(x=>x.id===id);
  if(!d) return;
  const dlBadge = deadlineBadge(d);
  document.getElementById('modalContent').innerHTML=`
    <h3 style="margin-bottom:6px">${escapeHtml(d.device)}</h3>
    <p style="color:#8a8f98;font-size:13px;margin-bottom:14px">${escapeHtml(d.id)} • ${escapeHtml(d.date)} • ${escapeHtml(d.deadline_type)} • deadline ${escapeHtml(d.deadline||'-')}</p>
    <div style="display:grid;gap:10px;font-size:13px">
      <div><strong>Pelanggan:</strong> ${escapeHtml(d.nama)} (${escapeHtml(d.wa)})</div>
      <div><strong>Keluhan:</strong> ${escapeHtml(d.keluhan)}</div>
      <div><strong>Kelengkapan:</strong> ${escapeHtml((d.kelengkapan||[]).join(', ')||'-')}</div>
      <div><strong>Teknisi:</strong> ${escapeHtml(d.teknisi)}</div>
      <div><strong>Biaya:</strong> Rp ${Number(d.biaya).toLocaleString('id-ID')}</div>
      <div><strong>Status:</strong> <span class="badge-status ${escapeHtml(d.status)}">${escapeHtml(d.status)}</span></div>
      <div><strong>Deadline:</strong> ${dlBadge} ${d.is_overdue?'<span style="background:#ef4444;color:#fff;padding:2px 6px;border-radius:8px;font-size:10px">OVERDUE</span>':''}</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:4px">
        <label style="font-size:11px">Ubah deadline:</label>
        <select id="modalDeadlineType" style="padding:6px 8px;border-radius:8px;border:1px solid #ececec;font-size:12px">
          <option value="harian" ${d.deadline_type==='harian'?'selected':''}>Harian (3 hari)</option>
          <option value="mingguan" ${d.deadline_type==='mingguan'?'selected':''}>Mingguan (7 hari)</option>
        </select>
        <button class="btn btn-ghost small" onclick="updateDeadline('${escapeHtml(d.id)}')">Simpan Deadline</button>
      </div>
    </div>
    <div style="margin-top:18px;display:flex;gap:10px">
      <button class="btn btn-dark" style="flex:1" onclick="window.print()">Cetak Nota</button>
      <button class="btn btn-ghost" style="flex:1" onclick="closeModal()">Tutup</button>
    </div>
  `;
  document.getElementById('modal').classList.add('show');
}
function closeModal(){ document.getElementById('modal').classList.remove('show'); }
function showToast(msg){
  const t=document.getElementById('toast');
  if(!t) return;
  t.textContent=msg; t.classList.add('show');
  setTimeout(()=>t.classList.remove('show'),2500);
}
// expose for inline onclick
window.switchView=switchView; window.handleServiceSubmit=handleServiceSubmit; window.resetForm=resetForm;
window.openDetail=openDetail; window.closeModal=closeModal; window.updateStatus=updateStatus;
window.handleLogout=handleLogout; window.handleCustomerSubmit=handleCustomerSubmit;
window.renderSemuaService=renderSemuaService; window.renderStatusView=renderStatusView;
window.loadApprovalData=loadApprovalData; window.approveUser=approveUser; window.rejectUser=rejectUser;
window.refreshPendingBadge=refreshPendingBadge; window.handleNotifClick=handleNotifClick;
window.openEditUserModal=openEditUserModal; window.closeUserModal=closeUserModal; window.submitUserEdit=submitUserEdit;
window.toggleFreezeUser=toggleFreezeUser; window.deleteUser=deleteUser; window.filterAllUsers=filterAllUsers; window.renderAllUsers=renderAllUsers;
window.setDeadlineFilter=setDeadlineFilter; window.updateDeadline=updateDeadline; window.updateDeadlinePreview=updateDeadlinePreview;
window.API_BASE=API_BASE;
