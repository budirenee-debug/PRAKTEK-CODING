// B_gadget POS - Hybrid: FastAPI + SQLite, fallback localStorage
const STORAGE_KEY = 'servicell_data_v1';
const API_BASE = localStorage.getItem('API_BASE') || 'http://localhost:8000/api';
let USE_API = true; // coba API dulu, fallback ke localStorage jika gagal

const defaultData = [
  {id:'INV-2026-0118', invoice:'INV-2026-0118', nama:'Renee Budiman', wa:'081234567890', device:'iPhone 11 64GB', keluhan:'LCD pecah & baterai drop', teknisi:'Andi', biaya:850000, status:'Dikerjakan', date:'2026-09-02', kelengkapan:['HP Saja','+ Charger']},
  {id:'INV-2026-0119', invoice:'INV-2026-0119', nama:'Dewi Lestari', wa:'082112345678', device:'Samsung A54', keluhan:'Mati total habis jatuh', teknisi:'Sinta', biaya:450000, status:'Antri', date:'2026-09-02', kelengkapan:['HP Saja']},
  {id:'INV-2026-0120', invoice:'INV-2026-0120', nama:'Budi Santoso', wa:'081345678901', device:'Xiaomi Redmi Note 12', keluhan:'Kamera belakang blur', teknisi:'Budi', biaya:250000, status:'Menunggu Sparepart', date:'2026-09-01', kelengkapan:['HP Saja','+ Dus']},
  {id:'INV-2026-0121', invoice:'INV-2026-0121', nama:'Citra Amelia', wa:'085678901234', device:'Oppo Reno 8', keluhan:'Speaker sember', teknisi:'Andi', biaya:180000, status:'Selesai', date:'2026-09-01', kelengkapan:['HP Saja']},
  {id:'INV-2026-0122', invoice:'INV-2026-0122', nama:'Fajar Pratama', wa:'081987654321', device:'iPhone XR', keluhan:'Face ID tidak berfungsi', teknisi:'Sinta', biaya:650000, status:'Antri', date:'2026-09-02', kelengkapan:['HP Saja','+ Charger']},
];

let data = [];

function normalize(item){
  // backend -> frontend shape
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
    estimasi_selesai: item.estimasi_selesai || null
  };
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
  const r = localStorage.getItem('role') || 'superadmin';
  const elU = document.getElementById('sidebar-username');
  const elR = document.getElementById('sidebar-role');
  if(elU) elU.textContent = u;
  if(elR) elR.textContent = r === 'superadmin' ? 'Superadmin • Full Access' : r;
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
  document.querySelectorAll('.tab').forEach(t=>t.addEventListener('click', ()=>{
    document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
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
    proses:['Proses Service','Tracking status pengerjaan teknisi secara real-time'],
    'bisa-diambil':['Bisa Diambil','Device siap, bisa diambil pelanggan'],
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
    'laporan-penjualan':['Laporan Penjualan','Pendapatan & penjualan']
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
  // jika API online, fetch stats real
  if(USE_API){
    apiFetch('/stats').then(s=>{
      document.getElementById('stat-masuk').textContent = s.total_masuk;
      document.getElementById('stat-proses').textContent = s.dalam_proses;
      document.getElementById('stat-selesai').textContent = s.selesai_hari_ini;
      // pendapatan
      const el = document.querySelector('.stat-card.dark h3');
      if(el) el.textContent = 'Rp ' + Number(s.estimasi_pendapatan).toLocaleString('id-ID');
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
function renderKanban(){
  const wrap=document.getElementById('kanban');
  if(!wrap) return;
  let filtered = data;
  if(statusFilter!=='all') filtered=data.filter(d=>d.status===statusFilter);
  if(pelangganFilter && statusFilter==='all'){
     filtered=filtered.filter(d=> (d.nama+d.device+d.keluhan).toLowerCase().includes(pelangganFilter));
  }
  const opts = statusOptions().map(s=>`<option>${s}</option>`).join('');
  wrap.innerHTML = filtered.map(d=>`
    <div class="service-card">
      <div class="service-card-head">
        <div><h4>${escapeHtml(d.device)}</h4><p>${escapeHtml(d.id)} • ${escapeHtml(d.nama)}</p></div>
        <span class="badge-status ${escapeHtml(d.status)}">${escapeHtml(d.status)}</span>
      </div>
      <p>📝 ${escapeHtml(d.keluhan)}</p>
      <div class="service-meta">
        <span class="meta-pill">👨‍🔧 ${escapeHtml(d.teknisi)}</span>
        <span class="meta-pill">💰 Rp ${Number(d.biaya).toLocaleString('id-ID')}</span>
        <span class="meta-pill">📦 ${escapeHtml((d.kelengkapan||[]).join(', '))}</span>
      </div>
      <div class="card-actions">
        <select onchange="updateStatus('${escapeHtml(d.id)}', this.value)" style="flex:1;padding:8px;border-radius:10px;border:1px solid #ececec;font-size:12px">
          <option disabled selected>Ubah status</option>
          ${opts}
        </select>
        <button class="btn btn-ghost small" onclick="openDetail('${escapeHtml(d.id)}')">Detail</button>
      </div>
    </div>
  `).join('') || `<div style="grid-column:1/-1;text-align:center;padding:40px;color:#8a8f98">Tidak ada service dengan status ini</div>`;
  document.querySelectorAll('.tab').forEach(tab=>{
    const f=tab.dataset.filter;
    const count = f==='all'? data.length : data.filter(d=>d.status===f).length;
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
  tbody.innerHTML = filtered.map(d=>`
    <tr>
      <td><strong>${escapeHtml(d.id)}</strong><br><span style="color:#8a8f98;font-size:11px">${escapeHtml(d.date)}</span></td>
      <td><div class="avatar-cell"><img src="https://i.pravatar.cc/100?u=${escapeHtml(d.wa)}"><div><strong>${escapeHtml(d.nama)}</strong><br><span style="color:#8a8f98">${escapeHtml(d.device)}</span></div></div></td>
      <td>${escapeHtml(d.keluhan)}</td>
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
  const filtered = data.filter(d=>d.status===statusName);
  const opts = statusOptions().map(s=>`<option>${s}</option>`).join('');
  wrap.innerHTML = filtered.map(d=>`
    <div class="service-card">
      <div class="service-card-head"><div><h4>${escapeHtml(d.device)}</h4><p>${escapeHtml(d.id)} • ${escapeHtml(d.nama)}</p></div><span class="badge-status ${escapeHtml(d.status)}">${escapeHtml(d.status)}</span></div>
      <p>📝 ${escapeHtml(d.keluhan)}</p>
      <div class="service-meta"><span class="meta-pill">👨‍🔧 ${escapeHtml(d.teknisi)}</span><span class="meta-pill">💰 Rp ${Number(d.biaya).toLocaleString('id-ID')}</span></div>
      <div class="card-actions"><select onchange="updateStatus('${escapeHtml(d.id)}', this.value)" style="flex:1;padding:8px;border-radius:10px;border:1px solid #ececec;font-size:12px"><option disabled selected>Ubah status</option>${opts}</select><button class="btn btn-ghost small" onclick="openDetail('${escapeHtml(d.id)}')">Detail</button></div>
    </div>
  `).join('') || `<div style="grid-column:1/-1;text-align:center;padding:40px;color:#8a8f98">Belum ada service dengan status <strong>${escapeHtml(statusName)}</strong></div>`;
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

  const payload = {
    nama, wa,
    device: device,
    imei: imei || null,
    keluhan,
    kelengkapan: [...selectedKelengkapan],
    biaya,
    teknisi,
    status: "Antri",
    estimasi_selesai: estimasi
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
  document.getElementById('modalContent').innerHTML=`
    <h3 style="margin-bottom:6px">${escapeHtml(d.device)}</h3>
    <p style="color:#8a8f98;font-size:13px;margin-bottom:14px">${escapeHtml(d.id)} • ${escapeHtml(d.date)}</p>
    <div style="display:grid;gap:10px;font-size:13px">
      <div><strong>Pelanggan:</strong> ${escapeHtml(d.nama)} (${escapeHtml(d.wa)})</div>
      <div><strong>Keluhan:</strong> ${escapeHtml(d.keluhan)}</div>
      <div><strong>Kelengkapan:</strong> ${escapeHtml((d.kelengkapan||[]).join(', ')||'-')}</div>
      <div><strong>Teknisi:</strong> ${escapeHtml(d.teknisi)}</div>
      <div><strong>Biaya:</strong> Rp ${Number(d.biaya).toLocaleString('id-ID')}</div>
      <div><strong>Status:</strong> <span class="badge-status ${escapeHtml(d.status)}">${escapeHtml(d.status)}</span></div>
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
window.API_BASE=API_BASE;
