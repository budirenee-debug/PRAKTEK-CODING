// Data dummy frontend only - localStorage
const STORAGE_KEY = 'servicell_data_v1';

const defaultData = [
  {id:'INV-2026-0118', nama:'Renee Budiman', wa:'081234567890', device:'iPhone 11 64GB', keluhan:'LCD pecah & baterai drop', teknisi:'Andi', biaya:850000, status:'Dikerjakan', date:'2026-09-02', kelengkapan:['HP Saja','+ Charger']},
  {id:'INV-2026-0119', nama:'Dewi Lestari', wa:'082112345678', device:'Samsung A54', keluhan:'Mati total habis jatuh', teknisi:'Sinta', biaya:450000, status:'Antri', date:'2026-09-02', kelengkapan:['HP Saja']},
  {id:'INV-2026-0120', nama:'Budi Santoso', wa:'081345678901', device:'Xiaomi Redmi Note 12', keluhan:'Kamera belakang blur', teknisi:'Budi', biaya:250000, status:'Menunggu Sparepart', date:'2026-09-01', kelengkapan:['HP Saja','+ Dus']},
  {id:'INV-2026-0121', nama:'Citra Amelia', wa:'085678901234', device:'Oppo Reno 8', keluhan:'Speaker sember', teknisi:'Andi', biaya:180000, status:'Selesai', date:'2026-09-01', kelengkapan:['HP Saja']},
  {id:'INV-2026-0122', nama:'Fajar Pratama', wa:'081987654321', device:'iPhone XR', keluhan:'Face ID tidak berfungsi', teknisi:'Sinta', biaya:650000, status:'Antri', date:'2026-09-02', kelengkapan:['HP Saja','+ Charger']},
];

let data = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null') || defaultData;
function save(){ localStorage.setItem(STORAGE_KEY, JSON.stringify(data)); }

let selectedKelengkapan = new Set();
let pelangganFilter = '';
let statusFilter = 'all';

// Init
document.addEventListener('DOMContentLoaded', ()=>{
  setupNavigation();
  setupChips();
  renderAll();
  updateInvoicePreview();
  document.getElementById('globalSearch').addEventListener('input', e=>{
    const q=e.target.value.toLowerCase();
    pelangganFilter = q;
    statusFilter = 'all';
    switchView('pelanggan');
    document.getElementById('searchPelanggan').value = q;
    renderPelanggan();
  });
  document.getElementById('searchPelanggan').addEventListener('input', e=>{
    pelangganFilter=e.target.value.toLowerCase(); renderPelanggan();
  });
  document.getElementById('filterDevice').addEventListener('change', renderPelanggan);
  document.getElementById('hamburger').addEventListener('click', ()=>document.getElementById('sidebar').classList.toggle('open'));
  document.querySelectorAll('.tab').forEach(t=>t.addEventListener('click', ()=>{
    document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
    t.classList.add('active');
    statusFilter=t.dataset.filter; renderKanban();
  }));
});

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
    'service-masuk':['Service Masuk','Input device baru & kelola antrian masuk'],
    pelanggan:['Data Pelanggan','Kelola 48 pelanggan loyal & riwayat service'],
    proses:['Proses Service','Tracking status pengerjaan teknisi secara real-time']
  };
  if(titles[view]){
    document.getElementById('page-title').textContent=titles[view][0];
    document.getElementById('page-subtitle').textContent=titles[view][1];
  }
  document.getElementById('sidebar').classList.remove('open');
  if(view==='dashboard') renderDashboard();
  if(view==='proses') renderKanban();
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

function updateStats(){
  document.getElementById('stat-masuk').textContent = data.length;
  document.getElementById('stat-proses').textContent = data.filter(d=>['Antri','Dikerjakan','Menunggu Sparepart'].includes(d.status)).length;
  document.getElementById('stat-selesai').textContent = data.filter(d=>d.status==='Selesai').length;
  document.getElementById('queueCount').textContent = data.length+' antrian';
  document.querySelector('.menu-item[data-view="service-masuk"] .badge').textContent = data.length;
}

function renderDashboard(){
  const tbody=document.querySelector('#tableDashboard tbody');
  tbody.innerHTML = data.slice(0,4).map(d=>`
    <tr>
      <td><strong>${d.id}</strong><br><span style="color:#8a8f98;font-size:11px">${d.date}</span></td>
      <td><div class="avatar-cell"><img src="https://i.pravatar.cc/100?u=${d.wa}"><div><strong>${d.nama}</strong><br><span style="color:#8a8f98">${d.device}</span></div></div></td>
      <td>${d.keluhan}</td>
      <td><span class="badge-status ${d.status}">${d.status}</span></td>
    </tr>
  `).join('');
}

function renderQueue(){
  const wrap=document.getElementById('queueList');
  wrap.innerHTML = data.slice(0,6).map(d=>`
    <div class="queue-item">
      <img src="https://i.pravatar.cc/100?u=${d.wa}">
      <div><strong>${d.nama}</strong><br><span>${d.device} • ${d.id}</span></div>
      <span class="price">Rp ${d.biaya.toLocaleString('id-ID')}</span>
    </div>
  `).join('');
}

function renderPelanggan(){
  const tbody=document.querySelector('#tablePelanggan tbody');
  const filterDevice=document.getElementById('filterDevice').value;
  let filtered=[...data];
  if(pelangganFilter) filtered=filtered.filter(d=> (d.nama+d.device+d.wa+d.id).toLowerCase().includes(pelangganFilter));
  if(filterDevice) filtered=filtered.filter(d=>d.device.includes(filterDevice));
  // group by nama for count demo, but just show rows
  tbody.innerHTML = filtered.map(d=>`
    <tr>
      <td><div class="avatar-cell"><img src="https://i.pravatar.cc/100?u=${d.wa}"><div><strong>${d.nama}</strong><br><span style="color:#8a8f98;font-size:12px">${d.wa}</span></div></div></td>
      <td>${d.device}</td>
      <td><span style="background:#f3f4f6;padding:4px 8px;border-radius:20px;font-size:12px">${Math.floor(Math.random()*5)+1}x</span></td>
      <td>${d.date}</td>
      <td><span class="badge-status Selesai">Member</span></td>
      <td><button class="btn btn-ghost small" onclick="openDetail('${d.id}')">Detail</button></td>
    </tr>
  `).join('') || `<tr><td colspan="6" style="text-align:center;padding:20px;color:#8a8f98">Tidak ada data</td></tr>`;
  document.getElementById('pelangganCount').textContent = filtered.length + ' pelanggan';
  document.getElementById('paginationInfo').textContent = `Menampilkan ${filtered.length} dari ${data.length}`;
}

function renderKanban(){
  const wrap=document.getElementById('kanban');
  let filtered = data;
  if(statusFilter!=='all') filtered=data.filter(d=>d.status===statusFilter);
  if(pelangganFilter && statusFilter==='all'){
     // also apply global search in kanban
     filtered=filtered.filter(d=> (d.nama+d.device+d.keluhan).toLowerCase().includes(pelangganFilter));
  }
  wrap.innerHTML = filtered.map(d=>`
    <div class="service-card">
      <div class="service-card-head">
        <div><h4>${d.device}</h4><p>${d.id} • ${d.nama}</p></div>
        <span class="badge-status ${d.status}">${d.status}</span>
      </div>
      <p>📝 ${d.keluhan}</p>
      <div class="service-meta">
        <span class="meta-pill">👨‍🔧 ${d.teknisi}</span>
        <span class="meta-pill">💰 Rp ${d.biaya.toLocaleString('id-ID')}</span>
        <span class="meta-pill">📦 ${d.kelengkapan.join(', ')}</span>
      </div>
      <div class="card-actions">
        <select onchange="updateStatus('${d.id}', this.value)" style="flex:1;padding:8px;border-radius:10px;border:1px solid #ececec;font-size:12px">
          <option disabled selected>Ubah status</option>
          <option>Antri</option><option>Dikerjakan</option><option>Menunggu Sparepart</option><option>Selesai</option>
        </select>
        <button class="btn btn-ghost small" onclick="openDetail('${d.id}')">Detail</button>
      </div>
    </div>
  `).join('') || `<div style="grid-column:1/-1;text-align:center;padding:40px;color:#8a8f98">Tidak ada service dengan status ini</div>`;
  // update tab counts
  document.querySelectorAll('.tab').forEach(tab=>{
    const f=tab.dataset.filter;
    const count = f==='all'? data.length : data.filter(d=>d.status===f).length;
    tab.querySelector('span').textContent = count;
  });
}

function updateStatus(id, newStatus){
  const item=data.find(d=>d.id===id);
  if(item){ item.status=newStatus; save(); renderAll(); showToast(`Status ${id} → ${newStatus}`); }
}

function handleServiceSubmit(e){
  e.preventDefault();
  const nama=document.getElementById('f-nama').value.trim();
  const wa=document.getElementById('f-wa').value.trim();
  const device=document.getElementById('f-device').value.trim();
  const imei=document.getElementById('f-imei').value.trim();
  const keluhan=document.getElementById('f-keluhan').value.trim();
  const biaya=parseInt(document.getElementById('f-biaya').value)||0;
  const teknisi=document.getElementById('f-teknisi').value;
  if(!nama||!wa||!device||!keluhan) return showToast('Lengkapi field wajib!');
  const newId='INV-2026-'+String(100+data.length+1).padStart(4,'0');
  data.unshift({id:newId, nama, wa, device: imei? `${device} • ${imei}`:device, keluhan, teknisi, biaya, status:'Antri', date:new Date().toISOString().slice(0,10), kelengkapan:[...selectedKelengkapan]});
  save(); renderAll(); resetForm(); showToast('Service berhasil disimpan! '+newId);
  switchView('proses');
}
function resetForm(){
  document.getElementById('serviceForm').reset();
  selectedKelengkapan.clear();
  document.querySelectorAll('.chip').forEach(c=>c.classList.remove('active'));
  updateInvoicePreview();
}
function updateInvoicePreview(){
  const next='INV-2026-'+String(100+data.length+1).padStart(4,'0');
  document.getElementById('invoicePreview').textContent=next;
}
function openDetail(id){
  const d=data.find(x=>x.id===id);
  if(!d) return;
  document.getElementById('modalContent').innerHTML=`
    <h3 style="margin-bottom:6px">${d.device}</h3>
    <p style="color:#8a8f98;font-size:13px;margin-bottom:14px">${d.id} • ${d.date}</p>
    <div style="display:grid;gap:10px;font-size:13px">
      <div><strong>Pelanggan:</strong> ${d.nama} (${d.wa})</div>
      <div><strong>Keluhan:</strong> ${d.keluhan}</div>
      <div><strong>Kelengkapan:</strong> ${d.kelengkapan.join(', ')||'-'}</div>
      <div><strong>Teknisi:</strong> ${d.teknisi}</div>
      <div><strong>Biaya:</strong> Rp ${d.biaya.toLocaleString('id-ID')}</div>
      <div><strong>Status:</strong> <span class="badge-status ${d.status}">${d.status}</span></div>
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
  t.textContent=msg; t.classList.add('show');
  setTimeout(()=>t.classList.remove('show'),2500);
}
// expose for inline onclick
window.switchView=switchView; window.handleServiceSubmit=handleServiceSubmit; window.resetForm=resetForm;
window.openDetail=openDetail; window.closeModal=closeModal; window.updateStatus=updateStatus;
