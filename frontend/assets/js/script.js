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
  {id:'INV-2026-0118', invoice:'INV-2026-0118', nama:'Renee Budiman', wa:'081234567890', device:'iPhone 11 64GB', keluhan:'LCD pecah & baterai drop', teknisi:'Andi', penerima:'Admin', biaya:850000, status:'Dikerjakan', date:'2026-09-02', estimasi_selesai:'2026-09-05', deadline:'2026-09-05', deadline_type:'harian', kelengkapan:['HP Saja','+ Charger']},
  {id:'INV-2026-0119', invoice:'INV-2026-0119', nama:'Dewi Lestari', wa:'082112345678', device:'Samsung A54', keluhan:'Mati total habis jatuh', teknisi:'Sinta', penerima:'Sinta', biaya:450000, status:'Antri', date:'2026-09-02', estimasi_selesai:'2026-09-06', deadline:'2026-09-06', deadline_type:'harian', kelengkapan:['HP Saja']},
  {id:'INV-2026-0120', invoice:'INV-2026-0120', nama:'Budi Santoso', wa:'081345678901', device:'Xiaomi Redmi Note 12', keluhan:'Kamera belakang blur', teknisi:'Budi', penerima:'Budi', biaya:250000, status:'Menunggu Sparepart', date:'2026-09-01', estimasi_selesai:'2026-09-08', deadline:'2026-09-08', deadline_type:'mingguan', kelengkapan:['HP Saja','+ Dus']},
  {id:'INV-2026-0121', invoice:'INV-2026-0121', nama:'Citra Amelia', wa:'085678901234', device:'Oppo Reno 8', keluhan:'Speaker sember', teknisi:'Andi', penerima:'Andi', biaya:180000, status:'Service Sukses', date:'2026-09-01', estimasi_selesai:'2026-09-04', deadline:'2026-09-04', deadline_type:'harian', kelengkapan:['HP Saja']},
  {id:'INV-2026-0122', invoice:'INV-2026-0122', nama:'Fajar Pratama', wa:'081987654321', device:'iPhone XR', keluhan:'Face ID tidak berfungsi', teknisi:'Sinta', penerima:'Admin', biaya:650000, status:'Antri', date:'2026-09-02', estimasi_selesai:'2026-09-09', deadline:'2026-09-09', deadline_type:'mingguan', kelengkapan:['HP Saja','+ Charger']},
];

let data = [];

// ---------- Inventory Sparepart ----------
const INVENTORY_KEY = 'b_gadget_inventory_v1';
const MERK_HITS = ['IPHONE','SAMSUNG','XIAOMI','OPPO','VIVO','INFINIX'];
const todayISO = () => new Date().toISOString().slice(0,10);
const defaultInventory = [
  {id:1, nama:'LCD iPhone 11', merk:'IPHONE', kategori:'Display', masuk:10, keluar:8, stok:2, harga:550000, tgl: todayISO()},
  {id:2, nama:'Baterai Samsung A54', merk:'SAMSUNG', kategori:'Baterai', masuk:15, keluar:3, stok:12, harga:280000, tgl: todayISO()},
  {id:3, nama:'Fleksibel Kamera Redmi Note 12', merk:'XIAOMI', kategori:'Kamera', masuk:8, keluar:2, stok:6, harga:120000, tgl: todayISO()},
  {id:4, nama:'LCD Oppo Reno 8', merk:'OPPO', kategori:'Display', masuk:12, keluar:4, stok:8, harga:420000, tgl: todayISO()},
  {id:5, nama:'Baterai Vivo Y12', merk:'VIVO', kategori:'Baterai', masuk:20, keluar:5, stok:15, harga:180000, tgl: todayISO()},
  {id:6, nama:'LCD Infinix Hot 12', merk:'INFINIX', kategori:'Display', masuk:9, keluar:7, stok:2, harga:250000, tgl: todayISO()},
  {id:7, nama:'IC Power Universal', merk:'LAIN', kategori:'Mesin', masuk:6, keluar:1, stok:5, harga:95000, tgl: todayISO()},
];
let inventory = [];
function normalizeMerk(m){
  if(!m) return 'LAIN';
  const up=String(m).trim().toUpperCase();
  return MERK_HITS.includes(up) ? up : 'LAIN';
}
function inferMerkFromNama(nama){
  if(!nama) return 'LAIN';
  const n=String(nama).toLowerCase();
  if(n.includes('iphone')) return 'IPHONE';
  if(n.includes('samsung')) return 'SAMSUNG';
  if(n.includes('xiaomi')||n.includes('redmi')||n.includes('poco')) return 'XIAOMI';
  if(n.includes('oppo')) return 'OPPO';
  if(n.includes('vivo')) return 'VIVO';
  if(n.includes('infinix')) return 'INFINIX';
  return 'LAIN';
}
function loadInventory(){
  try{
    const raw=localStorage.getItem(INVENTORY_KEY);
    if(raw){ inventory=JSON.parse(raw); if(!Array.isArray(inventory)||!inventory.length) inventory=[...defaultInventory]; }
    else inventory=[...defaultInventory];
  }catch{ inventory=[...defaultInventory]; }
  // migrasi: tambah merk & tgl jika belum ada (simple)
  let migrated=false;
  inventory.forEach(it=>{
    if(!it.merk){
      it.merk = inferMerkFromNama(it.nama);
      migrated=true;
    } else {
      const norm=normalizeMerk(it.merk);
      if(it.merk!==norm){ it.merk=norm; migrated=true; }
    }
    if(!it.tgl){
      it.tgl = todayISO();
      migrated=true;
    }
  });
  if(migrated) saveInventory();
}
function saveInventory(){ localStorage.setItem(INVENTORY_KEY, JSON.stringify(inventory)); }
function nextInventoryId(){ return inventory.length ? Math.max(...inventory.map(i=>i.id))+1 : 1; }

// ---------- Sparepart Usage Log (Proses Service -> Stok) ----------
const SPAREPART_USAGE_KEY='b_gadget_sparepart_usage_v1';
let serviceSpareparts={}; // { invoice: [{sparepartId, nama, merk, qty, harga, teknisi, date}] }
function loadSparepartUsage(){
  try{ const raw=localStorage.getItem(SPAREPART_USAGE_KEY); serviceSpareparts= raw? JSON.parse(raw) : {}; }catch{ serviceSpareparts={}; }
}
function saveSparepartUsage(){ localStorage.setItem(SPAREPART_USAGE_KEY, JSON.stringify(serviceSpareparts)); }
function getUsedCount(invoice){ const arr=serviceSpareparts[invoice]||[]; return arr.reduce((s,x)=>s+(x.qty||0),0); }

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
function formatTanggal(dateStr){
  if(!dateStr) return '-';
  const s = String(dateStr).slice(0,10);
  const parts = s.split('-');
  if(parts.length!==3) return s;
  const [y,m,d] = parts;
  const bulan = ['Jan','Feb','Mar','Apr','Mei','Jun','Jul','Agu','Sep','Okt','Nov','Des'];
  const idx = parseInt(m,10)-1;
  const mm = bulan[idx] || m;
  return `${d}-${mm}-${y}`;
}
function formatTanggalImage(dateStr){
  if(!dateStr) return '-';
  const s = String(dateStr).slice(0,10);
  const parts = s.split('-');
  if(parts.length!==3) return s;
  const [y,m,d] = parts;
  const bulan = ['Jan','Feb','Mar','Apr','Mei','Jun','Jul','Agu','Sep','Okt','Nov','Des'];
  const idx = parseInt(m,10)-1;
  const mm = bulan[idx] || m;
  return `${d} ${mm} ${y}`;
}
function hitungLama(dateStr){
  if(!dateStr) return '-';
  const today = new Date(); today.setHours(0,0,0,0);
  const tgl = new Date(String(dateStr).slice(0,10)); tgl.setHours(0,0,0,0);
  const diff = Math.round((today - tgl)/86400000);
  if(diff<0) return '0 Hari';
  return `${diff} Hari`;
}
// Realtime — jam terkini simple, update tiap detik
function updateRealtimeClock(){
  const now=new Date();
  const hari=['Minggu','Senin','Selasa','Rabu','Kamis','Jumat','Sabtu'][now.getDay()];
  const bulan=['Jan','Feb','Mar','Apr','Mei','Jun','Jul','Agu','Sep','Okt','Nov','Des'][now.getMonth()];
  const tgl=String(now.getDate()).padStart(2,'0');
  const thn=now.getFullYear();
  const jam=String(now.getHours()).padStart(2,'0');
  const menit=String(now.getMinutes()).padStart(2,'0');
  const detik=String(now.getSeconds()).padStart(2,'0');
  const str=`${hari}, ${tgl} ${bulan} ${thn} • ${jam}:${menit}:${detik}`;
  const el=document.getElementById('realtimeClock');
  if(el) el.textContent=str;
  const sub=document.getElementById('page-subtitle');
  const title=document.getElementById('page-title');
  if(sub && title && title.textContent.includes('Dashboard')){
    sub.textContent=`Ringkasan service hari ini — ${hari}, ${tgl} ${bulan} ${thn} • ${jam}:${menit}`;
  }
}
function cleanWA(wa){
  if(!wa) return '';
  let s = String(wa).replace(/\D/g,'');
  if(s.startsWith('0')) s = '62' + s.slice(1);
  else if(s.startsWith('620')) s = s; // already 62
  return s;
}
const WA_ICON = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style="vertical-align:middle"><path d="M19.05 4.94A9.88 9.88 0 0012 2C6.48 2 2 6.48 2 12c0 1.76.46 3.48 1.32 4.99L2 22l5.09-1.33A9.88 9.88 0 0012 22c5.52 0 10-4.48 10-10 0-2.64-1.03-5.12-2.95-6.94v-.12z" fill="#25D366"/><path d="M17.1 14.3c-.23-.12-1.35-.67-1.56-.75-.21-.08-.36-.12-.51.12-.15.23-.58.75-.71.9-.13.15-.25.17-.47.06-.22-.12-.94-.35-1.79-1.11-.66-.59-1.1-1.32-1.23-1.54-.13-.22-.01-.34.1-.45.1-.1.22-.25.33-.38.11-.12.15-.22.22-.37.07-.15.04-.27-.02-.38-.06-.11-.51-1.23-.7-1.68-.18-.44-.37-.38-.51-.39h-.43c-.15 0-.38.06-.58.27-.2.22-.77.75-.77 1.84s.79 2.13.9 2.28c.11.15 1.55 2.37 3.76 3.32.53.22.94.36 1.26.46.53.17 1.01.14 1.39.09.42-.06 1.35-.55 1.54-1.08.19-.53.19-.98.13-1.08-.06-.1-.21-.16-.43-.27z" fill="white"/></svg>`;
function openWhatsApp(wa, nama, device, invoice, keluhan){
  const clean = cleanWA(wa);
  if(!clean) return showToast('No WA tidak valid');
  const name = nama||'Pelanggan';
  const dev = device||'Device';
  const inv = invoice||'';
  const kel = keluhan||'';
  let msg = `Halo ${name} 👋\n`;
  msg += `Dari B_gadget POS Service HP\n`;
  if(inv) msg += `Invoice: ${inv}\n`;
  if(dev) msg += `Device: ${dev}\n`;
  if(kel) msg += `Keluhan: ${kel}\n`;
  msg += `\nTerima kasih 🙏`;
  // Use wa.me which will open WhatsApp Web/Desktop logged in on PC
  const url = `https://wa.me/${clean}?text=${encodeURIComponent(msg)}`;
  window.open(url, '_blank');
}
function normalize(item){
  // backend -> frontend shape — deadline sekarang = estimasi_selesai jika ada (jatuh tempo = estimasi)
  const dtype = (item.deadline_type || (item.estimasi_selesai ? ((new Date(item.estimasi_selesai)-new Date(item.date||new Date()))/(86400000) <=3 ? 'harian':'mingguan') : 'harian')).toLowerCase();
  let dl = item.deadline || item.estimasi_selesai || null;
  if(!dl && item.date){
    dl = computeDeadline(item.date, dtype);
  }
  // jika deadline masih berbeda dari estimasi dan estimasi ada, sinkronkan (deadline = estimasi)
  if(item.estimasi_selesai && dl !== item.estimasi_selesai){
    // backend sudah sync, tapi fallback client
    dl = item.estimasi_selesai;
  }
  let sisa = item.sisa_hari;
  if(sisa === undefined || sisa === null) sisa = dl ? computeSisa(dl) : null;
  let overdue = item.is_overdue;
  if(overdue === undefined || overdue === null){
    overdue = sisa !== null ? (sisa < 0 && !['Selesai','Service Sukses','Sudah Diambil','Dibatalkan','Service Failed'].includes(item.status)) : false;
  }
  // Normalisasi Selesai legacy → Service Sukses
  let normalizedStatus = item.status === 'Selesai' ? 'Service Sukses' : item.status;
  return {
    id: item.invoice || item.id,
    invoice: item.invoice || item.id,
    nama: item.nama,
    wa: item.wa,
    device: item.device,
    keluhan: item.keluhan,
    teknisi: item.teknisi || item.technician || '-',
    penerima: item.penerima || '-',
    biaya: item.biaya || 0,
    status: normalizedStatus,
    date: (item.date || '').slice(0,10),
    kelengkapan: Array.isArray(item.kelengkapan) ? item.kelengkapan : (typeof item.kelengkapan === 'string' ? JSON.parse(item.kelengkapan || '[]') : []),
    estimasi_selesai: item.estimasi_selesai || null,
    deadline_type: dtype,
    deadline: dl ? String(dl).slice(0,10) : null,
    sisa_hari: sisa,
    is_overdue: overdue
  };
}

function updateDeadlinePreview(){
  const estInput = document.getElementById('f-estimasi');
  const prev = document.getElementById('deadlinePreview');
  if(!prev) return;
  if(!estInput || !estInput.value){
    prev.textContent = 'Pilih Estimasi Selesai — deadline otomatis = tanggal estimasi';
    prev.style.color = '#8a8f98';
    return;
  }
  const val = estInput.value;
  const today = new Date(); today.setHours(0,0,0,0);
  const est = new Date(val); est.setHours(0,0,0,0);
  const diff = Math.round((est - today)/86400000);
  const type = diff <=3 ? 'harian' : 'mingguan';
  const baseColor = type==='mingguan' ? '#2563eb' : '#059669';
  let txt = `Deadline: ${formatTanggal(val)} • ${type} • `;
  if(diff<0) txt += `⚠ Overdue ${Math.abs(diff)} hari dari estimasi`;
  else if(diff===0) txt += `⏰ Hari ini (jatuh tempo)`;
  else txt += `⏳ ${diff} hari lagi menuju estimasi`;
  prev.textContent = txt;
  if(diff<0) prev.style.color = '#dc2626';
  else if(diff===0) prev.style.color = '#b45309';
  else prev.style.color = baseColor;
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

async function loadAvailableTechs(){
  // ambil daftar akun terdaftar yang bisa di-assign dari backend
  const fallback = [
    {username: 'Andi', role: 'teknisi', source: 'fallback'},
    {username: 'Sinta', role: 'teknisi', source: 'fallback'},
    {username: 'Budi', role: 'teknisi', source: 'fallback'}
  ];
  if(!USE_API){
    availableTechs = [...fallback];
    populateTeknisiSelect();
    return availableTechs;
  }
  try{
    const token = localStorage.getItem('access_token');
    const headers = token ? getAuthHeaders() : {'Content-Type':'application/json'};
    const res = await fetch(`${API_BASE}/auth/available-technicians`, {headers});
    if(!res.ok) throw new Error(await res.text());
    const rows = await res.json();
    // rows = [{username, role, source}]
    availableTechs = rows.length ? rows : [...fallback];
  }catch(e){
    console.warn('loadAvailableTechs gagal, fallback:', e.message);
    // coba fallback ke /technicians legacy
    try{
      const rows2 = await apiFetch('/technicians');
      if(Array.isArray(rows2) && rows2.length){
        availableTechs = rows2.map(r=>({username: r.nama || r.username, role:'teknisi', source:'technician'}));
      } else {
        availableTechs = [...fallback];
      }
    }catch{
      availableTechs = [...fallback];
    }
  }
  populateTeknisiSelect();
  return availableTechs;
}

function populateTeknisiSelect(){
  // isi dropdown Teknisi (Menunggu Teknisi + anggota terdaftar)
  const sel = document.getElementById('f-teknisi');
  if(sel){
    const currentVal = sel.value || 'Menunggu Teknisi';
    const opts = ['Menunggu Teknisi', ...availableTechs.map(t=>t.username)];
    const unique = [...new Set(opts)];
    sel.innerHTML = unique.map(name=>{
      const tech = availableTechs.find(t=>t.username===name);
      const label = tech ? `${name} — ${tech.role}` : name;
      const extra = name==='Menunggu Teknisi' ? ' (belum di-assign)' : '';
      return `<option value="${escapeHtml(name)}">${escapeHtml(label+extra)}</option>`;
    }).join('');
    if(unique.includes(currentVal)) sel.value = currentVal;
    else sel.value = 'Menunggu Teknisi';
  }
  // isi dropdown Penerima (anggota terdaftar — untuk Service Masuk)
  const selP = document.getElementById('f-penerima');
  if(selP){
    const curP = selP.value || '';
    // penerima: semua anggota + opsi kosong
    const members = availableTechs.length ? availableTechs : [];
    // fallback jika belum ada anggota (offline tanpa login) -> tampilkan Andi/Sinta/Budi + current user
    const fallbackMembers = members.length ? members : [
      {username:'Andi', role:'teknisi'}, {username:'Sinta', role:'teknisi'}, {username:'Budi', role:'teknisi'}
    ];
    const me = localStorage.getItem('username');
    let optsP = fallbackMembers.map(m=>m.username);
    if(me && !optsP.includes(me)) optsP.unshift(me);
    const uniqueP = [...new Set(optsP)];
    const hasPlaceholder = selP.querySelector('option[disabled]');
    // jika masih placeholder Memuat anggota..., ganti
    if(uniqueP.length){
      const prevVal = curP;
      selP.innerHTML = `<option value="" disabled ${!prevVal?'selected':''}>Pilih penerima</option>` + uniqueP.map(name=>{
        const m = fallbackMembers.find(x=>x.username===name) || availableTechs.find(x=>x.username===name);
        const label = m ? `${name} — ${m.role}` : name;
        const selAttr = name===prevVal ? 'selected' : '';
        return `<option value="${escapeHtml(name)}" ${selAttr}>${escapeHtml(label)}</option>`;
      }).join('');
      if(prevVal && uniqueP.includes(prevVal)) selP.value = prevVal;
    }
  }
}

async function assignTeknisi(invoice, newTeknisi){
  if(!invoice || !newTeknisi) return;
  const prev = data.find(d=>d.id===invoice)?.teknisi;
  if(prev===newTeknisi) return;
  try{
    if(USE_API){
      await apiFetch(`/services/${invoice}`, {method:'PATCH', body: JSON.stringify({teknisi: newTeknisi})});
      await loadData();
    } else {
      const item=data.find(d=>d.id===invoice);
      if(item){ item.teknisi=newTeknisi; saveLocal(); }
    }
    renderAll();
    renderSemuaService();
    showToast(`👨‍🔧 ${invoice} → teknisi: ${newTeknisi}`);
  }catch(e){
    showToast('Gagal assign teknisi: '+e.message);
  }
}

// ---------- App state ----------
let selectedKelengkapan = new Set();
let pelangganFilter = '';
let statusFilter = 'all';
let deadlineFilter = 'all'; // all, overdue, today, harian, mingguan
const PROSES_STATUSES = ['Antri','Menunggu Konfirmasi','Dikerjakan','Menunggu Sparepart']; // status yang tampil di tab Proses Service
let availableTechs = []; // cache akun terdaftar (teknisi/admin) + Technician legacy untuk assign di Semua Service
let currentPageProses = 1;
let currentPageSemua = 1;
const pageSize = 20;

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
  const dlRaw = d.deadline || '-';
  const dl = dlRaw !== '-' ? formatTanggal(dlRaw) : '-';
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
function avatarUrlFor(name, foto){
  if(foto) return foto;
  if(!name) return 'https://i.pravatar.cc/100?img=33';
  // deterministik: hash username -> 1..70
  let h=0; for(let i=0;i<name.length;i++) h=(h*31+name.charCodeAt(i))%70;
  const img=h+1;
  // pakai u param untuk konsistensi, fallback img
  return `https://i.pravatar.cc/100?u=${encodeURIComponent(name)}&img=${img}`;
}
function updateSidebarUser(){
  const u = localStorage.getItem('username') || 'Admin Toko';
  const r = localStorage.getItem('role') || '';
  const elU = document.getElementById('sidebar-username');
  const elR = document.getElementById('sidebar-role');
  const elA = document.getElementById('sidebar-avatar');
  if(elU) elU.textContent = u;
  if(elR) {
    if(r === 'superadmin') elR.textContent = 'Superadmin • Full Access';
    else if(r) elR.textContent = r;
    else elR.textContent = 'Belum login';
  }
  if(elA){
    // cari foto dari availableTechs jika ada
    const tech = availableTechs.find(t=>t.username===u);
    elA.src = avatarUrlFor(u, tech && tech.foto);
    elA.alt = u;
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

// ---------- Profil Pengguna ----------
async function loadProfil(){
  const elName=document.getElementById('profil-name');
  const elRole=document.getElementById('profil-role');
  const elStat=document.getElementById('profil-status');
  const elCreated=document.getElementById('profil-created');
  const elLast=document.getElementById('profil-lastlogin');
  const elAvatar=document.getElementById('profil-avatar');
  const inpUser=document.getElementById('p-username');
  const inpRole=document.getElementById('p-role');
  const token=localStorage.getItem('access_token');
  if(!token){
    if(elName) elName.textContent='Belum login';
    if(elRole) elRole.textContent='-';
    if(elStat) elStat.textContent='Silakan login dulu';
    showToast('⛔ Belum login — silakan login');
    return;
  }
  try{
    const res=await fetch(`${API_BASE}/auth/me`, {headers:getAuthHeaders()});
    if(!res.ok){ const t=await res.text(); throw new Error(t); }
    const me=await res.json();
    if(elName) elName.textContent=me.username;
    if(elRole) elRole.textContent=me.role;
    if(elStat) elStat.textContent=me.is_active ? '✅ Aktif' : '⏳ Menunggu persetujuan';
    if(elCreated) elCreated.textContent= me.created_at ? new Date(me.created_at).toLocaleString('id-ID') : '-';
    if(elLast) elLast.textContent= me.last_login ? new Date(me.last_login).toLocaleString('id-ID') : '-';
    const tech = availableTechs.find(t=>t.username===me.username);
    if(elAvatar) elAvatar.src=avatarUrlFor(me.username, tech && tech.foto);
    if(inpUser) inpUser.value=me.username;
    if(inpRole) inpRole.value=me.role;
    // sync sidebar juga
    localStorage.setItem('username', me.username);
    localStorage.setItem('role', me.role);
    updateSidebarUser();
  }catch(e){
    console.warn('loadProfil gagal', e.message);
    if(elStat) elStat.textContent='Gagal: '+ e.message.slice(0,120);
    showToast('Gagal load profil: '+e.message);
    // fallback dari localStorage
    const u=localStorage.getItem('username')||'-';
    const r=localStorage.getItem('role')||'-';
    if(elName) elName.textContent=u;
    if(elRole) elRole.textContent=r;
    if(inpUser) inpUser.value=u;
    if(inpRole) inpRole.value=r;
    if(elAvatar) elAvatar.src=avatarUrlFor(u);
  }
}
async function handleProfilUpdate(e){
  e.preventDefault();
  const u=document.getElementById('p-username').value.trim();
  const p=document.getElementById('p-password').value;
  const c=document.getElementById('p-confirm').value;
  if(!u || u.length<3) return showToast('Username minimal 3 karakter');
  if(p || c){
    if(p.length<6) return showToast('Password minimal 6 karakter');
    if(p!==c) return showToast('Konfirmasi password tidak cocok');
  }
  const payload={};
  if(u) payload.username=u;
  if(p) payload.password=p;
  try{
    const res=await fetch(`${API_BASE}/auth/me`, {method:'PATCH', headers:getAuthHeaders(), body:JSON.stringify(payload)});
    const j=await res.json();
    if(!res.ok) throw new Error(j.detail || 'Gagal update profil');
    showToast(`✅ Profil diperbarui → ${j.username}`);
    localStorage.setItem('username', j.username);
    localStorage.setItem('role', j.role);
    updateSidebarUser();
    await loadProfil();
    // kosongkan password fields
    document.getElementById('p-password').value='';
    document.getElementById('p-confirm').value='';
    if(USE_API) await loadAvailableTechs();
  }catch(err){
    showToast('Gagal update: '+err.message);
  }
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
  await loadAvailableTechs();
  loadInventory();
  loadAlat();
  loadSparepartUsage();
  renderAll();
  renderSemuaService();
  renderSparepart();
  renderAlat();
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
  // sparepart inventory listeners
  const sps=document.getElementById('searchSparepart'); if(sps) sps.addEventListener('input', renderSparepart);
  const fks=document.getElementById('filterKategoriSp'); if(fks) fks.addEventListener('change', renderSparepart);
  const fms=document.getElementById('filterMerkSp'); if(fms) fms.addEventListener('change', renderSparepart);
  // alat inventory listeners
  const sa=document.getElementById('searchAlat'); if(sa) sa.addEventListener('input', renderAlat);
  const fka=document.getElementById('filterKondisiAlat'); if(fka) fka.addEventListener('change', renderAlat);
  // auto stok akhir di form tambah: Masuk - Keluar
  const spM=document.getElementById('sp-masuk'), spK=document.getElementById('sp-keluar'), spS=document.getElementById('sp-stok');
  function syncStokPreview(){ if(spM && spK && spS){ const m=parseInt(spM.value)||0, k=parseInt(spK.value)||0; if(spS.value===''|| document.activeElement===spM || document.activeElement===spK){ /* jangan paksa timpa jika user isi manual */ if(!spS.dataset.manual || spS.value==='') spS.placeholder=`auto = ${m-k}`; } } }
  if(spM) spM.addEventListener('input', syncStokPreview);
  if(spK) spK.addEventListener('input', syncStokPreview);
  if(spS) spS.addEventListener('input', ()=>{ spS.dataset.manual = spS.value ? '1' : ''; });
  // swipe to close sidebar on mobile
  let touchStartX=0;
  document.addEventListener('touchstart', e=>{ touchStartX=e.touches[0].clientX; }, {passive:true});
  document.addEventListener('touchend', e=>{
    const diff=e.changedTouches[0].clientX - touchStartX;
    const sb=document.getElementById('sidebar');
    if(sb && sb.classList.contains('open') && diff < -50) closeSidebar();
    if(sb && !sb.classList.contains('open') && touchStartX<20 && diff>50) openSidebar();
  }, {passive:true});
  // klik di luar dropdown sparepart -> tutup semua
  document.addEventListener('click', e=>{
    const isInput=e.target.closest('[id^="spare-search-"]');
    const isDrop=e.target.closest('[id^="spare-dropdown-"]');
    const isSuggest=e.target.closest('[onclick*="suggestSparepart"]') || e.target.closest('[onclick*="selectSparepart"]');
    if(!isInput && !isDrop && !isSuggest){
      document.querySelectorAll('[id^="spare-dropdown-"]').forEach(d=>d.style.display='none');
    }
  });
  // cek health
  checkHealth();
  updateDeadlinePreview();
  // realtime clock — simple, tiap detik
  updateRealtimeClock();
  setInterval(updateRealtimeClock, 1000);
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
    proses:['Proses Service','Antri • Menunggu Konfirmasi • Dikerjakan • Menunggu Sparepart (status lain ada di menu masing-masing)'],
    'bisa-diambil':['Bisa Diambil','Device Selesai & siap diambil pelanggan (status Selesai otomatis masuk sini)'],
    'sudah-diambil':['Sudah Diambil','Riwayat device yang sudah diambil'],
    'service-failed':['Service Failed','Gagal diperbaiki — perlu follow-up'],
    'status-garansi':['Status Garansi','Service dalam masa garansi'],
    'inventory-sparepart':['Sparepart','Kelola stok: Masuk / Keluar / Stok Akhir / Harga — editable langsung'],
    'inventory-stok':['Stok','Ringkasan stok inventory'],
    'inventory-alat':['Alat','Peralatan teknisi'],
    'inventory-tambah':['Tambah Sparepart','Tambah barang masuk & harga'],
    'transaksi-penjualan':['Penjualan','Riwayat transaksi penjualan'],
    'transaksi-pembayaran':['Pembayaran','Metode & status pembayaran'],
    'laporan-service':['Laporan Service','Rekap service per periode'],
    'laporan-teknisi':['Laporan Teknisi','Performa teknisi — avatar sesuai foto profil'],
    'laporan-penjualan':['Laporan Penjualan','Pendapatan & penjualan'],
    'profil':['Atur Profil','Kelola username & password akun Anda — avatar sinkron dengan sidebar'],
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
  if(view==='semua-service'){ if(!availableTechs.length) loadAvailableTechs().then(renderSemuaService); else renderSemuaService(); }
  if(view==='service-masuk'){ if(!availableTechs.length) loadAvailableTechs(); else populateTeknisiSelect(); }
  if(view==='bisa-diambil') renderStatusView('kanbanBisaDiambil','Bisa Diambil');
  if(view==='sudah-diambil') renderStatusView('kanbanSudahDiambil','Sudah Diambil');
  if(view==='service-failed') renderStatusView('kanbanFailed','Service Failed');
  if(view==='status-garansi') renderStatusView('kanbanGaransi','Garansi');
  if(view==='inventory-sparepart') renderSparepart();
  if(view==='inventory-alat') renderAlat();
  if(view==='inventory-tambah'){ /* focus nama */ setTimeout(()=>document.getElementById('sp-nama')?.focus(),100); }
  if(view==='laporan-teknisi') renderLaporanTeknisi();
  if(view==='profil') loadProfil();
  if(view==='approval-akun') loadApprovalData();
  // +Service Baru hanya di 3 tab
  const btnBaru=document.getElementById('btnServiceBaru');
  if(btnBaru){
    const showIn=['semua-service','service-masuk','proses'];
    btnBaru.style.display= showIn.includes(view) ? '' : 'none';
  }
}

// Dashboard stat cards — klik → view masing-masing (simple)
function statGoMasuk(){ switchView('semua-service'); const s=document.getElementById('filterStatusSemua'); if(s){ s.value=''; renderSemuaService(); } }
function statGoProses(){ switchView('proses'); setDeadlineFilter('all'); statusFilter='all'; document.querySelectorAll('#view-proses .tab[data-filter]').forEach(b=>b.classList.toggle('active', b.dataset.filter==='all')); renderKanban(); }
function statGoSukses(){ switchView('semua-service'); setTimeout(()=>{ const s=document.getElementById('filterStatusSemua'); if(s){ s.value='Service Sukses'; renderSemuaService(); }},80); }
function statGoPendapatan(){ switchView('laporan-penjualan'); }
function statGoOverdue(){ switchView('proses'); setTimeout(()=> setDeadlineFilter('overdue'),80); }
function statGoToday(){ switchView('proses'); setTimeout(()=> setDeadlineFilter('today'),80); }
function statGoHarian(){ switchView('proses'); setTimeout(()=> setDeadlineFilter('harian'),80); }
function statGoMingguan(){ switchView('proses'); setTimeout(()=> setDeadlineFilter('mingguan'),80); }
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
  document.getElementById('stat-proses').textContent = data.filter(d=>['Antri','Menunggu Konfirmasi','Dikerjakan','Menunggu Sparepart'].includes(d.status)).length;
  document.getElementById('stat-selesai').textContent = data.filter(d=>['Selesai','Service Sukses'].includes(d.status)).length;
  document.getElementById('queueCount').textContent = data.length+' antrian';
  const badge = document.querySelector('.menu-item[data-view="service-masuk"] .badge');
  if(badge) badge.textContent = data.length;
  // deadline counts (client fallback)
  const overdueCount = data.filter(d=>d.is_overdue).length;
  const todayDl = data.filter(d=>d.deadline===new Date().toISOString().slice(0,10) && !['Selesai','Service Sukses','Sudah Diambil','Dibatalkan'].includes(d.status)).length;
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
  // render hits setelah stats — data sudah tersedia
  renderHitsIndicators();
}
function getBrandFromDevice(device){
  if(!device) return 'Lainnya';
  const first = String(device).trim().split(/\s+/)[0];
  const low = first.toLowerCase();
  const map = {
    'iphone':'iPhone','samsung':'Samsung','xiaomi':'Xiaomi','oppo':'Oppo','vivo':'Vivo','realme':'Realme',
    'infinix':'Infinix','poco':'POCO','huawei':'Huawei','oneplus':'OnePlus','nokia':'Nokia','asus':'ASUS',
    'lenovo':'Lenovo','tecno':'Tecno','itel':'itel'
  };
  if(map[low]) return map[low];
  // kapitalisasi huruf pertama
  return first.charAt(0).toUpperCase() + first.slice(1).toLowerCase();
}
function getKeluhanCategory(keluhan){
  if(!keluhan) return 'Lainnya';
  const k = String(keluhan).toLowerCase();
  // urutkan keyword paling spesifik / panjang dulu
  const mapping = [
    ['mati total','Mati Total'],
    ['face id','Face ID'],
    ['touchscreen','Touchscreen Error'],
    ['touch','Touchscreen'],
    ['lcd pecah','LCD Pecah'],
    ['lcd','LCD / Display'],
    ['layar','Layar'],
    ['baterai','Baterai Drop'],
    ['batre','Baterai Drop'],
    ['kamera','Kamera'],
    ['camera','Kamera'],
    ['speaker','Speaker Sember'],
    ['sember','Speaker Sember'],
    ['sinyal','Sinyal'],
    ['charger','Charger / Port'],
    ['cas','Charger'],
    ['mic','Mic'],
    ['blur','Kamera Blur'],
    ['pecah','LCD Pecah'],
    ['drop','Baterai Drop'],
  ];
  for(const [kw,label] of mapping){
    if(k.includes(kw)) return label;
  }
  // fallback: 2 kata pertama
  const words = String(keluhan).trim().split(/\s+/).slice(0,2).join(' ');
  return words.charAt(0).toUpperCase() + words.slice(1);
}
function renderHitsIndicators(){
  const brandWrap = document.getElementById('brandHitsList');
  const kelWrap = document.getElementById('keluhanHitsList');
  const brandEmpty = document.getElementById('brandHitsEmpty');
  const kelEmpty = document.getElementById('keluhanHitsEmpty');
  if(!brandWrap || !kelWrap) return;
  if(!data || !data.length){
    brandWrap.innerHTML = '';
    kelWrap.innerHTML = '';
    if(brandEmpty) brandEmpty.style.display='block';
    if(kelEmpty) kelEmpty.style.display='block';
    return;
  }
  // brand counts
  const brandCounts = {};
  data.forEach(d=>{ const b=getBrandFromDevice(d.device); brandCounts[b]=(brandCounts[b]||0)+1; });
  const brandSorted = Object.entries(brandCounts).sort((a,b)=>b[1]-a[1]).slice(0,5);
  const maxBrand = brandSorted[0] ? brandSorted[0][1] : 1;
  // keluhan counts
  const kelCounts = {};
  data.forEach(d=>{ const cat=getKeluhanCategory(d.keluhan); kelCounts[cat]=(kelCounts[cat]||0)+1; });
  const kelSorted = Object.entries(kelCounts).sort((a,b)=>b[1]-a[1]).slice(0,5);
  const maxKel = kelSorted[0] ? kelSorted[0][1] : 1;
  // render brand
  brandWrap.innerHTML = brandSorted.map(([name,cnt])=>{
    const pct = Math.round((cnt/maxBrand)*100);
    return `<div style="display:flex;align-items:center;gap:10px">
      <span style="flex:1;font-size:13px;font-weight:600">${escapeHtml(name)}</span>
      <div class="progress" style="flex:1.2;max-width:140px;height:8px;background:#f3f4f6"><div style="width:${pct}%;background:#111"></div></div>
      <span style="font-size:12px;font-weight:700;min-width:36px;text-align:right">${cnt} unit</span>
      <span style="font-size:11px;color:#8a8f98">${pct}%</span>
    </div>`;
  }).join('') || '<p style="font-size:12px;color:#8a8f98">Belum ada data</p>';
  if(brandEmpty) brandEmpty.style.display = brandSorted.length ? 'none' : 'block';
  // render keluhan
  kelWrap.innerHTML = kelSorted.map(([cat,cnt])=>{
    const pct = Math.round((cnt/maxKel)*100);
    const color = pct>=80 ? '#ef4444' : pct>=50 ? '#f59e0b' : '#111';
    return `<div style="display:flex;align-items:center;gap:10px">
      <span style="flex:1;font-size:13px;font-weight:600">${escapeHtml(cat)}</span>
      <div class="progress" style="flex:1.2;max-width:140px;height:8px;background:#f3f4f6"><div style="width:${pct}%;background:${color}"></div></div>
      <span style="font-size:12px;font-weight:700;min-width:36px;text-align:right">${cnt} kasus</span>
      <span style="font-size:11px;color:#8a8f98">${pct}%</span>
    </div>`;
  }).join('') || '<p style="font-size:12px;color:#8a8f98">Belum ada data</p>';
  if(kelEmpty) kelEmpty.style.display = kelSorted.length ? 'none' : 'block';
}
function renderLaporanTeknisi(){
  const tbody=document.getElementById('tbodyLaporanTeknisi');
  if(!tbody) return;
  // kumpulkan teknisi unik dari data + availableTechs (biar yang belum handle tetap muncul jika mau)
  const techNames=new Set();
  data.forEach(d=>{
    const t=(d.teknisi||'').trim();
    if(t && t!=='Menunggu Teknisi' && t!=='-' ) techNames.add(t);
  });
  // juga tambahkan dari availableTechs (yang role teknisi) agar laporan tetap tampil meski belum ada service
  availableTechs.filter(t=>t.role==='teknisi').forEach(t=>techNames.add(t.username));
  if(!techNames.size){
    // fallback dummy agar tabel tidak kosong saat demo
    ['Andi','Sinta','Budi'].forEach(n=>techNames.add(n));
  }
  const rows=[...techNames].map(name=>{
    const handle=data.filter(d=>d.teknisi===name).length;
    const sukses=data.filter(d=>d.teknisi===name && ['Service Sukses','Selesai'].includes(d.status)).length;
    const failed=data.filter(d=>d.teknisi===name && d.status==='Service Failed').length;
    const garansi=data.filter(d=>d.teknisi===name && d.status==='Garansi').length;
    // rating: 5 jika sukses==handle & handle>0, skala 1-5; minimal 3.5 jika handle>0 tapi sukses rendah
    let rating='-';
    if(handle>0){
      const ratio=sukses/handle;
      const val= (ratio*5).toFixed(1);
      // clamp 3.0-5.0 agar tidak jelek
      const clamped=Math.max(3.0, Math.min(5.0, parseFloat(val))).toFixed(1);
      rating= clamped + ' ★';
    }
    const techObj=availableTechs.find(t=>t.username===name);
    const foto= techObj && techObj.foto ? techObj.foto : null;
    const avatar=avatarUrlFor(name, foto);
    return {name,handle,sukses,failed,garansi,rating,avatar};
  }).sort((a,b)=> b.handle - a.handle);
  tbody.innerHTML=rows.map(r=>`
    <tr>
      <td><div class="avatar-cell" style="gap:10px"><img src="${escapeHtml(r.avatar)}" alt="${escapeHtml(r.name)}" style="width:32px;height:32px;border-radius:50%;object-fit:cover;border:1px solid #ececec" onerror="this.src='https://i.pravatar.cc/100?u=${encodeURIComponent(r.name)}'"><div><strong>${escapeHtml(r.name)}</strong><br><span style="font-size:11px;color:#8a8f98">${escapeHtml(availableTechs.find(t=>t.username===r.name)?.role||'teknisi')}</span></div></div></td>
      <td><span style="background:#f3f4f6;padding:4px 8px;border-radius:20px;font-size:12px;font-weight:600">${r.handle}</span></td>
      <td><span style="background:#ecfdf5;color:#059669;padding:4px 8px;border-radius:20px;font-size:12px;font-weight:600">${r.sukses}</span></td>
      <td><span style="${r.failed? 'background:#fef2f2;color:#dc2626':'background:#f3f4f6;color:#6b7280'};padding:4px 8px;border-radius:20px;font-size:12px">${r.failed}</span></td>
      <td style="font-size:13px">${r.rating}</td>
    </tr>
  `).join('') || `<tr><td colspan="5" style="text-align:center;padding:16px;color:#8a8f98">Belum ada data teknisi</td></tr>`;
}
// ---------- Sparepart Inventory (editable Merk/Masuk/Keluar/Stok Akhir/Harga) ----------
function merkBadgeStyle(m){
  const s={IPHONE:'background:#111;color:#fff;border-color:#111', SAMSUNG:'background:#eff6ff;color:#1d4ed8;border-color:#bfdbfe', XIAOMI:'background:#fff7ed;color:#c2410c;border-color:#fed7aa', OPPO:'background:#ecfdf5;color:#047857;border-color:#a7f3d0', VIVO:'background:#f5f3ff;color:#6d28d9;border-color:#ddd6fe', INFINIX:'background:#fffbeb;color:#b45309;border-color:#fde68a', LAIN:'background:#f3f4f6;color:#4b5563;border-color:#e5e7eb'};
  return s[m]||s['LAIN'];
}
function renderSparepart(){
  const tbody=document.getElementById('tbodySparepart');
  const countEl=document.getElementById('sparepartCount');
  const warnEl=document.getElementById('sparepartWarning');
  const sumEl=document.getElementById('sparepartSummary');
  if(!tbody) return;
  const q=(document.getElementById('searchSparepart')?.value||'').toLowerCase();
  const fCat=document.getElementById('filterKategoriSp')?.value||'';
  const fMerk=document.getElementById('filterMerkSp')?.value||'';
  let filtered=[...inventory];
  if(q) filtered=filtered.filter(i=> (i.nama + (i.merk||'') + i.kategori).toLowerCase().includes(q));
  if(fCat) filtered=filtered.filter(i=> i.kategori===fCat);
  if(fMerk){
    if(fMerk==='LAIN') filtered=filtered.filter(i=> normalizeMerk(i.merk)==='LAIN');
    else filtered=filtered.filter(i=> normalizeMerk(i.merk)===fMerk);
  }
  // sort: merk hits dulu (IPHONE,SAMSUNG,etc) lalu stok tipis
  const merkOrder={IPHONE:0,SAMSUNG:1,XIAOMI:2,OPPO:3,VIVO:4,INFINIX:5,LAIN:6};
  filtered.sort((a,b)=> (merkOrder[normalizeMerk(a.merk)]??6) - (merkOrder[normalizeMerk(b.merk)]??6) || a.stok - b.stok);
  if(!filtered.length){
    tbody.innerHTML=`<tr><td colspan="8" style="text-align:center;padding:18px;color:#8a8f98">Tidak ada sparepart${q||fCat||fMerk?' sesuai filter':''} — <a href="#" onclick="switchView('inventory-tambah');return false">Tambah item</a></td></tr>`;
  } else {
    tbody.innerHTML=filtered.map(it=>{
      const merkNorm=normalizeMerk(it.merk);
      const stokColor = it.stok<=2 ? '#fef2f2;color:#dc2626;border-color:#fecaca' : it.stok<=5 ? '#fffbeb;color:#b45309;border-color:#fde68a' : '#ecfdf5;color:#059669;border-color:#a7f3d0';
      const stokBg = it.stok<=2 ? '#fef2f2' : it.stok<=5 ? '#fffbeb' : '#ecfdf5';
      return `
      <tr>
        <td><div style="display:flex;flex-direction:column"><strong style="font-size:12px">${escapeHtml(it.nama)}</strong><span style="font-size:10px;color:#8a8f98">#${it.id} • Masuk ${it.masuk} → Keluar ${it.keluar} → akhir ${it.stok}</span></div></td>
        <td><span style="padding:4px 8px;border-radius:20px;font-size:11px;font-weight:700;border:1px solid;display:inline-block;${merkBadgeStyle(merkNorm)}">${escapeHtml(merkNorm)}</span></td>
        <td><span class="badge-status" style="background:#f3f4f6;border:1px solid #ececec;font-size:11px">${escapeHtml(it.kategori)}</span></td>
        <td style="text-align:center"><input type="number" min="0" value="${it.masuk}" id="sp-masuk-${it.id}" style="width:70px;padding:6px 8px;border:1px solid #ececec;border-radius:8px;text-align:center;font-size:12px" onchange="updateSparepartField(${it.id},'masuk',this.value)"></td>
        <td style="text-align:center"><input type="number" min="0" value="${it.keluar}" id="sp-keluar-${it.id}" style="width:70px;padding:6px 8px;border:1px solid #ececec;border-radius:8px;text-align:center;font-size:12px" onchange="updateSparepartField(${it.id},'keluar',this.value)"><div style="font-size:9px;color:#6b7280;margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:90px">${it.lastUsedBy? `<span onclick="openSparepartLog(${it.id})" style="cursor:pointer;color:#2563eb;text-decoration:underline" title="Klik lihat riwayat pakai ${escapeHtml(it.nama)}">👷 ${escapeHtml(it.lastUsedBy)}</span> • <span onclick="openDetail('${escapeHtml(it.lastUsedInvoice)}')" style="cursor:pointer;color:#059669;text-decoration:underline" title="Buka service ${escapeHtml(it.lastUsedInvoice)}">${escapeHtml(it.lastUsedInvoice||'')}</span>` : '<span style="color:#9ca3af">belum dipakai</span>'}${it.log && it.log.length? ` • <span onclick="openSparepartLog(${it.id})" style="cursor:pointer;color:#6b7280;text-decoration:underline" title="Lihat ${it.log.length} riwayat pakai">${it.log.length}x</span>` : ''}</div></td>
        <td style="text-align:center"><input type="number" min="0" value="${it.stok}" id="sp-stok-${it.id}" style="width:80px;padding:6px 8px;border:1px solid ${it.stok<=2?'#fecaca':'#ececec'};border-radius:8px;text-align:center;font-size:12px;font-weight:700;background:${stokBg};color:${it.stok<=2?'#dc2626':it.stok<=5?'#b45309':'#059669'}" onchange="updateSparepartField(${it.id},'stok',this.value)"></td>
        <td style="font-size:11px;color:#4b5563;white-space:nowrap;text-align:center">${escapeHtml(formatTanggal(it.tgl))}</td>
        <td style="text-align:right"><input type="number" min="0" step="1000" value="${it.harga}" id="sp-harga-${it.id}" style="width:110px;padding:6px 8px;border:1px solid #ececec;border-radius:8px;text-align:right;font-size:12px" onchange="updateSparepartField(${it.id},'harga',this.value)"><div style="font-size:10px;color:#8a8f98">Rp ${Number(it.harga).toLocaleString('id-ID')}</div></td>
        <td style="text-align:center">
          <div style="display:flex;gap:6px;justify-content:center;flex-wrap:wrap">
            <button class="btn btn-dark small" style="padding:5px 8px;font-size:11px" onclick="saveSparepartRow(${it.id})">💾 Simpan</button>
            <button class="btn btn-ghost small" style="padding:5px 8px;font-size:11px" onclick="openSpEditModal(${it.id})">✎ Edit</button>
            <button class="btn btn-ghost small" style="padding:5px 8px;font-size:11px;color:#dc2626;border-color:#fecaca" onclick="deleteSparepart(${it.id})">🗑</button>
          </div>
        </td>
      </tr>`;
    }).join('');
  }
  if(countEl) countEl.textContent=filtered.length+' item';
  const lowCount=inventory.filter(i=>i.stok<=2).length;
  if(warnEl) warnEl.style.display= lowCount ? 'inline-block' : 'none';
  if(warnEl) warnEl.textContent= lowCount ? `⚠ ${lowCount} stok tipis` : '';
  if(sumEl){
    const totalVal=inventory.reduce((s,i)=> s + (i.stok * i.harga),0);
    sumEl.textContent= `${inventory.length} item • Total nilai stok: Rp ${Number(totalVal).toLocaleString('id-ID')} • Menampilkan ${filtered.length}`;
  }
}
function updateSparepartField(id, field, val){
  const it=inventory.find(x=>x.id===id);
  if(!it) return;
  const n=parseInt(val)||0;
  if(field==='masuk') it.masuk=n;
  else if(field==='keluar') it.keluar=n;
  else if(field==='stok') it.stok=n;
  else if(field==='harga') it.harga=n;
  it.tgl=todayISO();
  saveInventory();
  // update warna stok cell secara live
  if(field==='stok' || field==='masuk' || field==='keluar'){
    const stokInput=document.getElementById(`sp-stok-${id}`);
    if(stokInput){
      const v=parseInt(stokInput.value)||0;
      stokInput.style.background = v<=2 ? '#fef2f2' : v<=5 ? '#fffbeb' : '#ecfdf5';
      stokInput.style.color = v<=2 ? '#dc2626' : v<=5 ? '#b45309' : '#059669';
      stokInput.style.borderColor = v<=2 ? '#fecaca' : '#ececec';
    }
  }
}
function saveSparepartRow(id){
  const it=inventory.find(x=>x.id===id);
  if(!it) return;
  // baca ulang dari input untuk pastikan
  const masukEl=document.getElementById(`sp-masuk-${id}`);
  const keluarEl=document.getElementById(`sp-keluar-${id}`);
  const stokEl=document.getElementById(`sp-stok-${id}`);
  const hargaEl=document.getElementById(`sp-harga-${id}`);
  if(masukEl) it.masuk=parseInt(masukEl.value)||0;
  if(keluarEl) it.keluar=parseInt(keluarEl.value)||0;
  if(stokEl) it.stok=parseInt(stokEl.value)||0;
  if(hargaEl) it.harga=parseInt(hargaEl.value)||0;
  it.tgl=todayISO();
  saveInventory();
  renderSparepart();
  showToast(`✅ ${it.nama} disimpan — Masuk ${it.masuk}, Keluar ${it.keluar}, Stok ${it.stok}, Rp ${Number(it.harga).toLocaleString('id-ID')}`);
}
function deleteSparepart(id){
  const it=inventory.find(x=>x.id===id);
  if(!it) return;
  if(!confirm(`Hapus "${it.nama}"?`)) return;
  inventory=inventory.filter(x=>x.id!==id);
  saveInventory();
  renderSparepart();
  showToast(`🗑 ${it.nama} dihapus`);
}
function handleSparepartAdd(e){
  e.preventDefault();
  const nama=document.getElementById('sp-nama').value.trim();
  const merkRaw=document.getElementById('sp-merk')?.value||'LAIN';
  const merk=normalizeMerk(merkRaw);
  const kategori=document.getElementById('sp-kategori').value;
  const masuk=parseInt(document.getElementById('sp-masuk').value)||0;
  const keluar=parseInt(document.getElementById('sp-keluar').value)||0;
  let stokRaw=document.getElementById('sp-stok').value;
  const harga=parseInt(document.getElementById('sp-harga').value)||0;
  if(!nama) return showToast('Nama part wajib');
  if(!merk) return showToast('Merk wajib');
  if(!kategori) return showToast('Kategori wajib');
  if(harga<=0) return showToast('Harga wajib >0');
  let stok = stokRaw==='' ? (masuk - keluar) : parseInt(stokRaw)||0;
  if(stok<0) stok=0;
  // cek duplikat nama
  if(inventory.some(i=>i.nama.toLowerCase()===nama.toLowerCase())) return showToast('Nama part sudah ada — pakai Edit');
  const newItem={id:nextInventoryId(), nama, merk, kategori, masuk, keluar, stok, harga, tgl: todayISO()};
  inventory.unshift(newItem);
  saveInventory();
  e.target.reset();
  showToast(`✅ ${nama} ditambahkan — Stok ${stok}`);
  switchView('inventory-sparepart');
  renderSparepart();
}
function openSpEditModal(id){
  const it=inventory.find(x=>x.id===id);
  if(!it) return showToast('Item tidak ditemukan');
  document.getElementById('spEditId').value=it.id;
  document.getElementById('spEditNama').value=it.nama;
  const mEl=document.getElementById('spEditMerk'); if(mEl) mEl.value=normalizeMerk(it.merk);
  document.getElementById('spEditKategori').value=it.kategori;
  document.getElementById('spEditMasuk').value=it.masuk;
  document.getElementById('spEditKeluar').value=it.keluar;
  document.getElementById('spEditStok').value=it.stok;
  document.getElementById('spEditHarga').value=it.harga;
  document.getElementById('spEditModal').classList.add('show');
}
function closeSpEditModal(){ document.getElementById('spEditModal').classList.remove('show'); }
function submitSpEdit(e){
  e.preventDefault();
  const id=parseInt(document.getElementById('spEditId').value);
  const it=inventory.find(x=>x.id===id);
  if(!it) return;
  const nama=document.getElementById('spEditNama').value.trim();
  const merk=normalizeMerk(document.getElementById('spEditMerk')?.value||'LAIN');
  const kategori=document.getElementById('spEditKategori').value;
  const masuk=parseInt(document.getElementById('spEditMasuk').value)||0;
  const keluar=parseInt(document.getElementById('spEditKeluar').value)||0;
  const stok=parseInt(document.getElementById('spEditStok').value)||0;
  const harga=parseInt(document.getElementById('spEditHarga').value)||0;
  if(!nama) return showToast('Nama wajib');
  // cek duplikat kecuali diri sendiri
  if(inventory.some(x=>x.id!==id && x.nama.toLowerCase()===nama.toLowerCase())) return showToast('Nama sudah dipakai item lain');
  it.nama=nama; it.merk=merk; it.kategori=kategori; it.masuk=masuk; it.keluar=keluar; it.stok=stok; it.harga=harga; it.tgl=todayISO();
  saveInventory();
  closeSpEditModal();
  renderSparepart();
  showToast(`✎ ${nama} diperbarui`);
}
function resetSparepartDummy(){
  if(!confirm('Reset ke data dummy awal? Data saat ini akan tertimpa.')) return;
  inventory=[...defaultInventory];
  saveInventory();
  renderSparepart();
  showToast('🔄 Inventory direset ke dummy');
}
function openSparepartLog(id){
  const it=inventory.find(x=>x.id===id);
  if(!it) return showToast('Sparepart tidak ditemukan');
  const log=it.log||[];
  const merkNorm=normalizeMerk(it.merk);
  const html=`
    <h3 style="margin-bottom:4px;display:flex;align-items:center;gap:8px"><span style="padding:4px 8px;border-radius:20px;font-size:11px;border:1px solid;${merkBadgeStyle(merkNorm)}">${escapeHtml(merkNorm)}</span> ${escapeHtml(it.nama)}</h3>
    <p style="font-size:11px;color:#6b7280;margin-bottom:10px">${escapeHtml(it.kategori)} • Masuk ${it.masuk} • Keluar ${it.keluar} • Stok ${it.stok} • Rp ${Number(it.harga).toLocaleString('id-ID')} • Tgl ${escapeHtml(formatTanggal(it.tgl))}</p>
    <div style="display:flex;gap:6px;margin-bottom:10px;flex-wrap:wrap">
      <span style="font-size:11px;background:#f3f4f6;padding:4px 8px;border-radius:20px">Terakhir: ${it.lastUsedBy ? `${escapeHtml(it.lastUsedBy)} • ${escapeHtml(it.lastUsedInvoice||'-')} • ${escapeHtml(formatTanggal(it.lastUsedDate||it.tgl))}` : 'belum dipakai'}</span>
      <span style="font-size:11px;background:#ecfdf5;color:#059669;padding:4px 8px;border-radius:20px">${log.length} riwayat</span>
    </div>
    <div style="max-height:300px;overflow:auto;border:1px solid #ececec;border-radius:10px">
      <table class="table compact" style="font-size:11px">
        <thead><tr><th>Tgl</th><th>Invoice</th><th>Teknisi (profil)</th><th>Qty</th></tr></thead>
        <tbody>
          ${log.length ? log.map(l=>`<tr><td>${escapeHtml(formatTanggal(l.date))}</td><td><a href="#" onclick="closeModal();openDetail('${escapeHtml(l.invoice)}');return false" style="color:#2563eb;text-decoration:underline">${escapeHtml(l.invoice)}</a></td><td><span style="display:flex;align-items:center;gap:6px;cursor:pointer;color:#2563eb;text-decoration:underline" title="Profil ${escapeHtml(l.teknisi)}" onclick="closeModal();switchView('laporan-teknisi')"><img src="${escapeHtml(avatarUrlFor(l.teknisi))}" style="width:20px;height:20px;border-radius:50%;border:1px solid #ececec" onerror="this.style.display='none'"> ${escapeHtml(l.teknisi)}</span></td><td>x${l.qty}</td></tr>`).join('') : `<tr><td colspan="4" style="text-align:center;padding:16px;color:#8a8f98">Belum ada riwayat — pakai sparepart dari Proses Service</td></tr>`}
        </tbody>
      </table>
    </div>
    <div style="margin-top:12px;display:flex;gap:8px">
      <button class="btn btn-dark small" style="flex:1" onclick="closeModal()">Tutup</button>
      <button class="btn btn-ghost small" style="flex:1" onclick="closeModal();switchView('inventory-sparepart')">← Kembali Stok</button>
    </div>
  `;
  document.getElementById('modalContent').innerHTML=html;
  document.getElementById('modal').classList.add('show');
}
// ---------- Pakai Sparepart di Proses Service (otomatis kurangi stok, catat teknisi) ----------
function sparepartSelectOptions(filterQ=''){
  if(!inventory.length) return '<option value="">Stok kosong — tambah di Sparepart</option>';
  const q=(filterQ||'').toLowerCase().trim();
  let list=[...inventory];
  if(q) list=list.filter(it=> (`${it.merk} ${it.nama} ${it.kategori}`.toLowerCase().includes(q)));
  if(!list.length) return '<option value="" disabled>Tidak ada hasil untuk "'+escapeHtml(filterQ)+'"</option>';
  return list.map(it=>{
    const merk=normalizeMerk(it.merk);
    const dis = it.stok<=0 ? 'disabled' : '';
    const stokTxt = it.stok<=0 ? 'HABIS' : `stok ${it.stok}`;
    return `<option value="${it.id}" ${dis}>${escapeHtml(merk)} ${escapeHtml(it.nama)} — ${stokTxt} • Rp ${Number(it.harga).toLocaleString('id-ID')}</option>`;
  }).join('');
}
function filterSparepartSelect(invoice){
  const searchEl=document.getElementById(`spare-search-${invoice}`);
  const sel=document.getElementById(`spare-select-${invoice}`);
  if(!sel) return;
  const q= searchEl ? searchEl.value : '';
  const curVal=sel.value;
  const baseOpts=`<option value="">Pilih Sparepart...</option><option value="none">— Tidak Ada —</option>`;
  const filteredOpts=sparepartSelectOptions(q);
  sel.innerHTML = baseOpts + filteredOpts;
  if([...sel.options].some(o=>o.value===curVal)) sel.value=curVal;
  const info=document.getElementById(`spare-info-${invoice}`);
  if(info){
    if(q && filteredOpts.includes('Tidak ada hasil')) info.textContent=`Tidak ada hasil untuk "${q}"`;
    else if(q) {
      const cnt=(filteredOpts.match(/<option/g)||[]).length;
      info.textContent=`${cnt} hasil untuk "${q}"`;
    } else info.textContent='';
  }
}
function filterSparepartInput(invoice){
  const input=document.getElementById(`spare-search-${invoice}`);
  const dropdown=document.getElementById(`spare-dropdown-${invoice}`);
  const hidden=document.getElementById(`spare-select-${invoice}`);
  if(!input || !dropdown) return;
  const q=input.value.toLowerCase().trim();
  let list=[...inventory];
  if(q) list=list.filter(it=> (`${it.merk||''} ${it.nama} ${it.kategori}`.toLowerCase().includes(q)));
  let html=`<div data-value="none" onclick="selectSparepart('${escapeHtml(invoice)}','none','— Tidak Ada —')" style="padding:8px 10px;cursor:pointer;font-size:11px;border-bottom:1px solid #f3f4f6;background:#f9fafb"><strong>— Tidak Ada —</strong> <span style="color:#6b7280">(tidak potong stok)</span></div>`;
  if(!list.length){
    html+=`<div style="padding:10px;text-align:center;color:#8a8f98;font-size:11px">Tidak ada hasil untuk "${escapeHtml(input.value)}"</div>`;
  } else {
    html+= list.slice(0,20).map(it=>{
      const merk=normalizeMerk(it.merk);
      const stokTxt= it.stok<=0 ? 'HABIS' : `stok ${it.stok}`;
      const dis= it.stok<=0 ? 'opacity:.5' : '';
      const label=`${merk} ${it.nama}`;
      return `<div data-value="${it.id}" onclick="selectSparepart('${escapeHtml(invoice)}','${it.id}','${escapeHtml(label)}')" style="padding:8px 10px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;font-size:11px;border-bottom:1px solid #f9fafb;${dis}"><div><strong>${escapeHtml(merk)}</strong> ${escapeHtml(it.nama)}<br><span style="font-size:10px;color:#6b7280">${escapeHtml(it.kategori)} • Rp ${Number(it.harga).toLocaleString('id-ID')}</span></div><span style="font-size:10px;padding:3px 7px;border-radius:20px;background:${it.stok<=2?'#fef2f2;color:#dc2626':'#ecfdf5;color:#059669'}">${stokTxt}</span></div>`;
    }).join('');
    if(list.length>20) html+=`<div style="padding:6px;text-align:center;font-size:10px;color:#6b7280">+ ${list.length-20} lainnya — ketik lebih spesifik</div>`;
  }
  dropdown.innerHTML=html;
  dropdown.style.display='block';
}
function showSparepartDropdown(invoice){
  const input=document.getElementById(`spare-search-${invoice}`);
  if(input && !input.value){
    // tampilkan semua + Tidak Ada saat fokus kosong
    filterSparepartInput(invoice);
  } else {
    filterSparepartInput(invoice);
  }
}
function selectSparepart(invoice, id, label){
  const input=document.getElementById(`spare-search-${invoice}`);
  const hidden=document.getElementById(`spare-select-${invoice}`);
  const dropdown=document.getElementById(`spare-dropdown-${invoice}`);
  if(hidden) hidden.value=id;
  if(input) input.value=label;
  if(dropdown) dropdown.style.display='none';
}
function suggestSparepart(invoice){
  const svc=data.find(d=>d.id===invoice);
  if(!svc) return showToast('Service tidak ditemukan');
  const merk=normalizeMerk(getBrandFromDevice(svc.device));
  const kelCat=getKeluhanCategory(svc.keluhan);
  const katMap={'LCD Pecah':'Display','LCD / Display':'Display','Layar':'Display','Baterai Drop':'Baterai','Kamera':'Kamera','Kamera Blur':'Kamera','Speaker Sember':'Konsumsi','Sinyal':'Mesin','Charger / Port':'Konsumsi','Mic':'Konsumsi','Touchscreen':'Display','Touchscreen Error':'Display','Face ID':'Kamera','Mati Total':'Mesin'};
  const kategori=katMap[kelCat]||'';
  let candidates=inventory.filter(it=>{
    const m=normalizeMerk(it.merk);
    return m===merk || it.kategori===kategori;
  });
  if(!candidates.length) candidates=inventory.filter(it=> normalizeMerk(it.merk)===merk);
  if(!candidates.length && kategori) candidates=inventory.filter(it=> it.kategori===kategori);
  if(!candidates.length) candidates=inventory.filter(it=> it.stok>0).slice(0,3);
  const input=document.getElementById(`spare-search-${invoice}`);
  const hidden=document.getElementById(`spare-select-${invoice}`);
  const dropdown=document.getElementById(`spare-dropdown-${invoice}`);
  if(!input || !hidden || !dropdown) return;
  if(!candidates.length){
    showToast('Tidak ada suggest — ketik manual y12 / merk');
    filterSparepartInput(invoice);
    return;
  }
  // build dropdown with suggest on top
  let html=`<div data-value="none" onclick="selectSparepart('${escapeHtml(invoice)}','none','— Tidak Ada —')" style="padding:8px 10px;cursor:pointer;font-size:11px;border-bottom:1px solid #f3f4f6;background:#f9fafb"><strong>— Tidak Ada —</strong> <span style="color:#6b7280">(tidak potong stok)</span></div>`;
  html+=`<div style="padding:6px 10px;font-size:10px;font-weight:700;color:#059669;background:#ecfdf5;border-bottom:1px solid #a7f3d0">💡 Suggest untuk ${escapeHtml(merk)} ${escapeHtml(kelCat)} (${candidates.length}) — klik untuk pilih</div>`;
  html+=candidates.slice(0,10).map(it=>{
    const m=normalizeMerk(it.merk);
    const stokTxt=it.stok<=0?'HABIS':`stok ${it.stok}`;
    const dis=it.stok<=0?'opacity:.5;pointer-events:none':'';
    const label=`${m} ${it.nama}`;
    return `<div data-value="${it.id}" onclick="selectSparepart('${escapeHtml(invoice)}','${it.id}','${escapeHtml(label)}')" style="padding:8px 10px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;font-size:11px;border-bottom:1px solid #f9fafb;${dis}"><div><strong>${escapeHtml(m)}</strong> ${escapeHtml(it.nama)}<br><span style="font-size:10px;color:#6b7280">${escapeHtml(it.kategori)} • Rp ${Number(it.harga).toLocaleString('id-ID')}</span></div><span style="font-size:10px;padding:3px 7px;border-radius:20px;background:${it.stok<=2?'#fef2f2;color:#dc2626':'#ecfdf5;color:#059669'}">${stokTxt}</span></div>`;
  }).join('');
  // auto-select first
  const firstAvail=candidates.find(c=>c.stok>0) || candidates[0];
  if(firstAvail){
    const label=`${normalizeMerk(firstAvail.merk)} ${firstAvail.nama}`;
    hidden.value=String(firstAvail.id);
    input.value=label;
    dropdown.innerHTML=html;
    dropdown.style.display='block';
    showToast(`💡 Suggest: ${label} untuk ${merk} ${kelCat} — stok ${firstAvail.stok}`);
  } else {
    hidden.value='';
    input.value='';
    dropdown.innerHTML=html;
    dropdown.style.display='block';
    showToast(`💡 Suggest: ${candidates.length} sparepart untuk ${merk}/${kategori} (stok tipis)`);
  }
}
function renderUsedSpareparts(invoice){
  const arr=serviceSpareparts[invoice]||[];
  if(!arr.length) return '';
  return `<div style="margin-top:6px;padding:6px 8px;background:#ecfdf5;border:1px solid #a7f3d0;border-radius:8px;font-size:11px"><strong>🔧 Terpakai (${arr.length}):</strong> ${arr.map(u=>`${escapeHtml(u.merk)} ${escapeHtml(u.nama)} x${u.qty} oleh ${escapeHtml(u.teknisi)}`).join(', ')}</div>`;
}
function pakaiSparepart(invoice){
  const sel=document.getElementById(`spare-select-${invoice}`);
  if(!sel || !sel.value) return showToast('Pilih sparepart dulu');
  if(sel.value==='none'){
    showToast('ℹ️ Tidak Ada sparepart dipilih — stok tidak berubah');
    const input=document.getElementById(`spare-search-${invoice}`);
    const dropdown=document.getElementById(`spare-dropdown-${invoice}`);
    // biarkan input tampil "Tidak Ada" sebentar lalu kosongkan
    if(input) input.value='— Tidak Ada —';
    setTimeout(()=>{
      if(input) input.value='';
      sel.value='';
      if(dropdown) dropdown.style.display='none';
    }, 800);
    const info=document.getElementById(`spare-info-${invoice}`);
    if(info) info.textContent='';
    return;
  }
  const spId=parseInt(sel.value);
  const sp=inventory.find(i=>i.id===spId);
  if(!sp) return showToast('Sparepart tidak ditemukan');
  if(sp.stok<=0) return showToast(`⚠ Stok ${sp.nama} habis`);
  const svc=data.find(d=>d.id===invoice);
  if(!svc) return showToast('Service tidak ditemukan');
  const teknisi=svc.teknisi && svc.teknisi!=='Menunggu Teknisi' && svc.teknisi!=='-' ? svc.teknisi : (localStorage.getItem('username')||'Teknisi');
  const qtyEl=document.getElementById(`spare-qty-${invoice}`);
  let qty= qtyEl ? parseInt(qtyEl.value)||1 : 1;
  if(qty<1) qty=1;
  if(qty>sp.stok) return showToast(`Stok tidak cukup (sisa ${sp.stok}) — kurangi qty`);
  // update inventory
  sp.keluar += qty;
  sp.stok = Math.max(0, sp.stok - qty);
  sp.tgl = todayISO();
  sp.lastUsedBy = teknisi;
  sp.lastUsedInvoice = invoice;
  sp.lastUsedDate = new Date().toISOString().slice(0,10);
  if(!sp.log) sp.log=[];
  sp.log.unshift({invoice, teknisi, qty, date: sp.lastUsedDate});
  if(sp.log.length>20) sp.log=sp.log.slice(0,20);
  // log per service
  if(!serviceSpareparts[invoice]) serviceSpareparts[invoice]=[];
  serviceSpareparts[invoice].push({sparepartId: sp.id, nama: sp.nama, merk: normalizeMerk(sp.merk), qty, harga: sp.harga, teknisi, date: sp.lastUsedDate});
  saveInventory();
  saveSparepartUsage();
  renderSparepart();
  renderKanban();
  renderMenungguTeknisiBlock();
  showToast(`🔧 ${normalizeMerk(sp.merk)} ${sp.nama} x${qty} dipakai ${teknisi} untuk ${invoice} — stok sisa ${sp.stok}`);
}

// ---------- Alat Inventory (editable per baris seperti Sparepart) ----------
const ALAT_KEY='b_gadget_alat_v1';
const defaultAlat = [
  {id:1, nama:'Blower', kondisi:'Baik', peminjam:'-', masuk:2, keluar:0, stok:2, harga:350000},
  {id:2, nama:'Microscope', kondisi:'Perlu Kalibrasi', peminjam:'-', masuk:1, keluar:0, stok:1, harga:2500000},
  {id:3, nama:'Solder Station', kondisi:'Baik', peminjam:'Andi', masuk:3, keluar:1, stok:2, harga:800000},
  {id:4, nama:'Power Supply', kondisi:'Baik', peminjam:'-', masuk:2, keluar:0, stok:2, harga:600000},
];
let alatInventory=[];
function loadAlat(){
  try{
    const raw=localStorage.getItem(ALAT_KEY);
    if(raw){ alatInventory=JSON.parse(raw); if(!Array.isArray(alatInventory)||!alatInventory.length) alatInventory=[...defaultAlat]; }
    else alatInventory=[...defaultAlat];
  }catch{ alatInventory=[...defaultAlat]; }
}
function saveAlat(){ localStorage.setItem(ALAT_KEY, JSON.stringify(alatInventory)); }
function nextAlatId(){ return alatInventory.length ? Math.max(...alatInventory.map(a=>a.id))+1 : 1; }
function kondisiBadge(k){
  if(k==='Baik') return 'background:#ecfdf5;color:#059669;border-color:#a7f3d0';
  if(k==='Perlu Kalibrasi') return 'background:#fffbeb;color:#b45309;border-color:#fde68a';
  if(k==='Rusak') return 'background:#fef2f2;color:#dc2626;border-color:#fecaca';
  if(k==='Dipinjam') return 'background:#eff6ff;color:#1d4ed8;border-color:#bfdbfe';
  return 'background:#f3f4f6;color:#4b5563;border-color:#e5e7eb';
}
function populateAlatPeminjamSelect(){
  const sel=document.getElementById('alatEditPeminjam');
  if(!sel) return;
  const cur=sel.value||'-';
  const opts=['-', ...availableTechs.map(t=>t.username)];
  const uniq=[...new Set(opts)];
  sel.innerHTML=uniq.map(n=>`<option value="${escapeHtml(n)}" ${n===cur?'selected':''}>${escapeHtml(n)}</option>`).join('');
}
function renderAlat(){
  const tbody=document.getElementById('tbodyAlat');
  const countEl=document.getElementById('alatCount');
  const warnEl=document.getElementById('alatWarning');
  const sumEl=document.getElementById('alatSummary');
  if(!tbody) return;
  const q=(document.getElementById('searchAlat')?.value||'').toLowerCase();
  const fK=document.getElementById('filterKondisiAlat')?.value||'';
  let filtered=[...alatInventory];
  if(q) filtered=filtered.filter(a=> (a.nama+a.peminjam+a.kondisi).toLowerCase().includes(q));
  if(fK) filtered=filtered.filter(a=> a.kondisi===fK);
  // sort: rusak/kalibrasi dulu
  const order={Rusak:0,'Perlu Kalibrasi':1,Dipinjam:2,Baik:3};
  filtered.sort((a,b)=> (order[a.kondisi]??9)-(order[b.kondisi]??9) || a.stok-b.stok);
  if(!filtered.length){
    tbody.innerHTML=`<tr><td colspan="8" style="text-align:center;padding:18px;color:#8a8f98">Tidak ada alat${q||fK?' sesuai filter':''} — <a href="#" onclick="openAlatAddModal();return false">Tambah alat</a></td></tr>`;
  } else {
    const peminjamOptions=['-', ...availableTechs.map(t=>t.username)];
    tbody.innerHTML=filtered.map(it=>{
      const stokBg= it.stok<=1 ? '#fef2f2' : it.stok===0 ? '#fef2f2' : '#ecfdf5';
      const stokColor= it.stok<=1 ? '#dc2626' : '#059669';
      const stokBorder= it.stok<=1 ? '#fecaca' : '#ececec';
      const kondisiOpts=['Baik','Perlu Kalibrasi','Rusak','Dipinjam'].map(k=>`<option ${k===it.kondisi?'selected':''}>${k}</option>`).join('');
      const peminjamOpts=[...new Set(peminjamOptions)].map(n=>`<option value="${escapeHtml(n)}" ${n===it.peminjam?'selected':''}>${escapeHtml(n)}</option>`).join('');
      const kondisiStyle=kondisiBadge(it.kondisi);
      return `
      <tr>
        <td><strong style="font-size:12px">${escapeHtml(it.nama)}</strong><div style="font-size:10px;color:#8a8f98">#${it.id}</div></td>
        <td><select id="alat-kondisi-${it.id}" style="padding:6px 8px;border-radius:8px;border:1px solid #ececec;font-size:11px;font-weight:600;${kondisiStyle}" onchange="updateAlatField(${it.id},'kondisi',this.value)">${kondisiOpts}</select></td>
        <td><select id="alat-peminjam-${it.id}" style="padding:6px 8px;border-radius:8px;border:1px solid #ececec;font-size:11px" onchange="updateAlatField(${it.id},'peminjam',this.value)">${peminjamOpts}</select></td>
        <td style="text-align:center"><input type="number" min="0" value="${it.masuk}" id="alat-masuk-${it.id}" style="width:65px;padding:6px 8px;border:1px solid #ececec;border-radius:8px;text-align:center;font-size:12px" onchange="updateAlatField(${it.id},'masuk',this.value)"></td>
        <td style="text-align:center"><input type="number" min="0" value="${it.keluar}" id="alat-keluar-${it.id}" style="width:65px;padding:6px 8px;border:1px solid #ececec;border-radius:8px;text-align:center;font-size:12px" onchange="updateAlatField(${it.id},'keluar',this.value)"></td>
        <td style="text-align:center"><input type="number" min="0" value="${it.stok}" id="alat-stok-${it.id}" style="width:70px;padding:6px 8px;border:1px solid ${stokBorder};border-radius:8px;text-align:center;font-size:12px;font-weight:700;background:${stokBg};color:${stokColor}" onchange="updateAlatField(${it.id},'stok',this.value)"></td>
        <td style="text-align:right"><input type="number" min="0" step="1000" value="${it.harga}" id="alat-harga-${it.id}" style="width:105px;padding:6px 8px;border:1px solid #ececec;border-radius:8px;text-align:right;font-size:12px" onchange="updateAlatField(${it.id},'harga',this.value)"><div style="font-size:10px;color:#8a8f98">Rp ${Number(it.harga).toLocaleString('id-ID')}</div></td>
        <td style="text-align:center"><div style="display:flex;gap:6px;justify-content:center;flex-wrap:wrap"><button class="btn btn-dark small" style="padding:5px 8px;font-size:11px" onclick="saveAlatRow(${it.id})">💾 Simpan</button><button class="btn btn-ghost small" style="padding:5px 8px;font-size:11px" onclick="openAlatEditModal(${it.id})">✎ Edit</button><button class="btn btn-ghost small" style="padding:5px 8px;font-size:11px;color:#dc2626;border-color:#fecaca" onclick="deleteAlat(${it.id})">🗑</button></div></td>
      </tr>`;
    }).join('');
  }
  if(countEl) countEl.textContent=filtered.length+' alat';
  const needCount=alatInventory.filter(a=> a.kondisi!=='Baik' || a.stok<=1).length;
  if(warnEl) warnEl.style.display= needCount?'inline-block':'none';
  if(warnEl) warnEl.textContent= needCount? `⚠ ${needCount} perlu perhatian`:'';
  if(sumEl){
    const totalVal=alatInventory.reduce((s,a)=> s + (a.stok*a.harga),0);
    sumEl.textContent=`${alatInventory.length} alat • Total nilai: Rp ${Number(totalVal).toLocaleString('id-ID')} • Menampilkan ${filtered.length}`;
  }
}
function updateAlatField(id, field, val){
  const it=alatInventory.find(x=>x.id===id);
  if(!it) return;
  if(field==='kondisi') it.kondisi=val;
  else if(field==='peminjam') it.peminjam=val;
  else {
    const n=parseInt(val)||0;
    if(field==='masuk') it.masuk=n;
    else if(field==='keluar') it.keluar=n;
    else if(field==='stok') it.stok=n;
    else if(field==='harga') it.harga=n;
  }
  // auto set kondisi Dipinjam jika peminjam != -
  if(field==='peminjam'){
    if(val!=='-' && it.kondisi==='Baik') it.kondisi='Dipinjam';
    if(val==='-' && it.kondisi==='Dipinjam') it.kondisi='Baik';
  }
  saveAlat();
  // live warna stok
  if(field==='stok'){
    const el=document.getElementById(`alat-stok-${id}`);
    if(el){
      const v=parseInt(el.value)||0;
      el.style.background = v<=1 ? '#fef2f2' : '#ecfdf5';
      el.style.color = v<=1 ? '#dc2626' : '#059669';
      el.style.borderColor = v<=1 ? '#fecaca' : '#ececec';
    }
  }
  if(field==='kondisi'){
    const sel=document.getElementById(`alat-kondisi-${id}`);
    if(sel) sel.style.cssText=`padding:6px 8px;border-radius:8px;border:1px solid #ececec;font-size:11px;font-weight:600;${kondisiBadge(val)}`;
  }
}
function saveAlatRow(id){
  const it=alatInventory.find(x=>x.id===id);
  if(!it) return;
  const kEl=document.getElementById(`alat-kondisi-${id}`);
  const pEl=document.getElementById(`alat-peminjam-${id}`);
  const mEl=document.getElementById(`alat-masuk-${id}`);
  const klEl=document.getElementById(`alat-keluar-${id}`);
  const sEl=document.getElementById(`alat-stok-${id}`);
  const hEl=document.getElementById(`alat-harga-${id}`);
  if(kEl) it.kondisi=kEl.value;
  if(pEl) it.peminjam=pEl.value;
  if(mEl) it.masuk=parseInt(mEl.value)||0;
  if(klEl) it.keluar=parseInt(klEl.value)||0;
  if(sEl) it.stok=parseInt(sEl.value)||0;
  if(hEl) it.harga=parseInt(hEl.value)||0;
  saveAlat();
  renderAlat();
  showToast(`✅ ${it.nama} disimpan — ${it.kondisi} • ${it.peminjam} • Stok ${it.stok}`);
}
function deleteAlat(id){
  const it=alatInventory.find(x=>x.id===id);
  if(!it) return;
  if(!confirm(`Hapus alat "${it.nama}"?`)) return;
  alatInventory=alatInventory.filter(x=>x.id!==id);
  saveAlat();
  renderAlat();
  showToast(`🗑 ${it.nama} dihapus`);
}
function openAlatAddModal(){
  document.getElementById('alatEditId').value='';
  document.getElementById('alatModalTitle').textContent='+ Tambah Alat';
  document.getElementById('alatEditNama').value='';
  document.getElementById('alatEditKondisi').value='Baik';
  populateAlatPeminjamSelect();
  document.getElementById('alatEditPeminjam').value='-';
  document.getElementById('alatEditMasuk').value=1;
  document.getElementById('alatEditKeluar').value=0;
  document.getElementById('alatEditStok').value=1;
  document.getElementById('alatEditHarga').value='';
  document.getElementById('alatEditModal').classList.add('show');
}
function openAlatEditModal(id){
  const it=alatInventory.find(x=>x.id===id);
  if(!it) return showToast('Alat tidak ditemukan');
  document.getElementById('alatModalTitle').textContent='✎ Edit Alat';
  document.getElementById('alatEditId').value=it.id;
  document.getElementById('alatEditNama').value=it.nama;
  document.getElementById('alatEditKondisi').value=it.kondisi;
  populateAlatPeminjamSelect();
  document.getElementById('alatEditPeminjam').value=it.peminjam;
  document.getElementById('alatEditMasuk').value=it.masuk;
  document.getElementById('alatEditKeluar').value=it.keluar;
  document.getElementById('alatEditStok').value=it.stok;
  document.getElementById('alatEditHarga').value=it.harga;
  document.getElementById('alatEditModal').classList.add('show');
}
function closeAlatModal(){ document.getElementById('alatEditModal').classList.remove('show'); }
function submitAlatEdit(e){
  e.preventDefault();
  const idRaw=document.getElementById('alatEditId').value;
  const nama=document.getElementById('alatEditNama').value.trim();
  const kondisi=document.getElementById('alatEditKondisi').value;
  const peminjam=document.getElementById('alatEditPeminjam').value;
  const masuk=parseInt(document.getElementById('alatEditMasuk').value)||0;
  const keluar=parseInt(document.getElementById('alatEditKeluar').value)||0;
  const stok=parseInt(document.getElementById('alatEditStok').value)||0;
  const harga=parseInt(document.getElementById('alatEditHarga').value)||0;
  if(!nama) return showToast('Nama alat wajib');
  if(harga<0) return showToast('Harga tidak valid');
  if(idRaw===''){
    // tambah baru
    if(alatInventory.some(a=>a.nama.toLowerCase()===nama.toLowerCase())) return showToast('Nama alat sudah ada');
    const newItem={id:nextAlatId(), nama, kondisi, peminjam, masuk, keluar, stok, harga};
    alatInventory.unshift(newItem);
    saveAlat();
    closeAlatModal();
    renderAlat();
    showToast(`✅ ${nama} ditambahkan`);
  } else {
    const id=parseInt(idRaw);
    const it=alatInventory.find(x=>x.id===id);
    if(!it) return;
    if(alatInventory.some(a=>a.id!==id && a.nama.toLowerCase()===nama.toLowerCase())) return showToast('Nama sudah dipakai alat lain');
    it.nama=nama; it.kondisi=kondisi; it.peminjam=peminjam; it.masuk=masuk; it.keluar=keluar; it.stok=stok; it.harga=harga;
    saveAlat();
    closeAlatModal();
    renderAlat();
    showToast(`✎ ${nama} diperbarui`);
  }
}
function resetAlatDummy(){
  if(!confirm('Reset alat ke dummy awal?')) return;
  alatInventory=[...defaultAlat];
  saveAlat();
  renderAlat();
  showToast('🔄 Alat direset ke dummy');
}

function renderDashboard(){
  const tbody=document.querySelector('#tableDashboard tbody');
  if(!tbody) return;
  tbody.innerHTML = data.slice(0,4).map(d=>`
    <tr>
      <td><strong>${escapeHtml(d.id)}</strong><br><span style="color:#8a8f98;font-size:11px">${escapeHtml(formatTanggal(d.date))}</span></td>
      <td><div class="avatar-cell"><img src="https://i.pravatar.cc/100?u=${escapeHtml(d.wa)}"><div><strong>${escapeHtml(d.nama)}</strong><br><span style="color:#8a8f98">${escapeHtml(d.device)}</span></div></div></td>
      <td>${escapeHtml(d.keluhan)}</td>
      <td><span class="badge-status ${escapeHtml(badgeClassForStatus(d.status))}">${escapeHtml(displayStatus(d.status))}</span></td>
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
      <td>${escapeHtml(formatTanggal(d.date))}</td>
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
  return ['Antri','Menunggu Konfirmasi','Dikerjakan','Menunggu Sparepart','Service Sukses','Bisa Diambil','Sudah Diambil','Service Failed','Garansi','Dibatalkan'];
}
// helper untuk badge class — Service Sukses pakai style Selesai (hijau)
function badgeClassForStatus(s){
  if(s==='Service Sukses' || s==='Selesai') return 'Selesai';
  return s;
}
function displayStatus(s){
  return s==='Selesai' ? 'Service Sukses' : s;
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
  // Basis: 4 status yang tampil di tab Proses Service (Antri, Menunggu Konfirmasi, Dikerjakan, Menunggu Sparepart)
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
        <span class="badge-status ${escapeHtml(badgeClassForStatus(d.status))}">${escapeHtml(displayStatus(d.status))}</span>
      </div>
      <p>📝 ${escapeHtml(d.keluhan)}</p>
      <div class="service-meta">
        <span class="meta-pill">👨‍🔧 ${escapeHtml(d.teknisi)}</span>
        <span class="meta-pill">💰 Rp ${Number(d.biaya).toLocaleString('id-ID')}</span>
        <span class="meta-pill">📦 ${escapeHtml((d.kelengkapan||[]).join(', '))}</span>
        ${deadlineBadge(d)}
      </div>
      <div style="margin-top:8px;padding:10px;background:#f9fafb;border:1px solid #ececec;border-radius:10px">
        <div style="font-size:11px;font-weight:600;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center"><span>🔧 Sparepart Dipakai</span><span style="font-size:10px;color:#8a8f98">suggest → pilih → Pakai</span></div>
        <div style="display:flex;gap:6px;align-items:flex-start">
          <div style="position:relative;flex:1">
            <input type="text" id="spare-search-${escapeHtml(d.id)}" placeholder="Pilih sparepart..." style="width:100%;padding:7px 8px;border:1px solid #ececec;border-radius:8px;font-size:11px" oninput="filterSparepartInput('${escapeHtml(d.id)}')" onfocus="showSparepartDropdown('${escapeHtml(d.id)}')" autocomplete="off">
            <input type="hidden" id="spare-select-${escapeHtml(d.id)}" value="">
            <div id="spare-dropdown-${escapeHtml(d.id)}" style="display:none;position:absolute;top:100%;left:0;right:0;background:#fff;border:1px solid #ececec;border-radius:8px;max-height:160px;overflow:auto;z-index:10;box-shadow:0 4px 12px rgba(0,0,0,.08);margin-top:4px"></div>
          </div>
          <button class="btn btn-ghost small" style="padding:7px 10px;font-size:11px;white-space:nowrap" onclick="suggestSparepart('${escapeHtml(d.id)}')" title="Suggest sesuai merk & keluhan">💡</button>
          <input type="number" id="spare-qty-${escapeHtml(d.id)}" value="1" min="1" style="width:60px;padding:7px 8px;border:1px solid #ececec;border-radius:8px;font-size:11px;text-align:center" title="Qty">
          <button class="btn btn-dark small" style="padding:7px 10px;font-size:11px;white-space:nowrap" onclick="pakaiSparepart('${escapeHtml(d.id)}')">Pakai</button>
        </div>
        ${renderUsedSpareparts(d.id)}
        ${(()=>{ const s=inventory.find(x=>x.stok<=2 && x.stok>0); return s? `<div style="font-size:10px;color:#dc2626;margin-top:4px">⚠ Stok tipis: ${escapeHtml(s.merk)} ${escapeHtml(s.nama)} sisa ${s.stok}</div>` : inventory.find(x=>x.stok===0)? `<div style="font-size:10px;color:#dc2626;margin-top:4px">⚠ Ada sparepart habis — cek Sparepart</div>` : ''; })()}
      </div>
      <div class="card-actions">
        <select onchange="updateStatus('${escapeHtml(d.id)}', this.value)" style="flex:1;padding:8px;border-radius:10px;border:1px solid #ececec;font-size:12px">
          <option disabled selected>Ubah status</option>
          ${opts}
        </select>
        <button class="btn btn-ghost small" onclick="openWhatsApp('${escapeHtml(d.wa)}','${escapeHtml(d.nama)}','${escapeHtml(d.device)}','${escapeHtml(d.id)}','${escapeHtml(d.keluhan)}')" style="background:#dcfce7;border-color:#bbf7d0;color:#166534" title="Direct WA">${WA_ICON}</button>
        <button class="btn btn-ghost small" onclick="openDetail('${escapeHtml(d.id)}')">Detail</button>
      </div>
    </div>
  `).join('') || `<div style="grid-column:1/-1;text-align:center;padding:40px;color:#8a8f98">Tidak ada service dengan status Antri / Menunggu Konfirmasi / Dikerjakan / Menunggu Sparepart</div>`;
  // update hitungan tab hanya untuk tab filter di view-proses
  document.querySelectorAll('#view-proses .tab[data-filter]').forEach(tab=>{
    const f=tab.dataset.filter;
    const count = f==='all'? data.filter(d=> PROSES_STATUSES.includes(d.status)).length : data.filter(d=>d.status===f).length;
    const sp = tab.querySelector('span');
    if(sp) sp.textContent = count;
  });
}
function renderMenungguTeknisiBlock(){
  const block=document.getElementById('menungguTeknisiBlock');
  const countEl=document.getElementById('menungguCount');
  const listEl=document.getElementById('menungguList');
  if(!block||!countEl||!listEl) return;
  // tunggu teknisi = teknisi === Menunggu Teknisi / - / kosong
  const menunggu = data.filter(d=> d.teknisi==='Menunggu Teknisi' || !d.teknisi || d.teknisi==='-' || d.teknisi==='Menunggu Teknisi');
  // jika ada search/filter di Semua Service, tetap tampilkan semua yang menunggu (highlight), tapi kalau user filter Service Sukses etc tetap tampilkan blok agar awareness
  if(!menunggu.length){ block.style.display='none'; return; }
  block.style.display='block';
  countEl.textContent = menunggu.length + ' device';
  const baseTechOpts = ['Menunggu Teknisi', ...availableTechs.map(t=>t.username)];
  listEl.innerHTML = menunggu.slice(0,12).map(d=>{
    const uniqOpts = [...new Set([...baseTechOpts, d.teknisi].filter(Boolean))];
    const optsHtml = uniqOpts.map(name=>{
      const sel = name===d.teknisi ? 'selected' : '';
      const tech = availableTechs.find(t=>t.username===name);
      const label = tech ? `${name} (${tech.role})` : name;
      return `<option value="${escapeHtml(name)}" ${sel}>${escapeHtml(label)}</option>`;
    }).join('');
    return `<div style="background:#fff;border:1px solid #fde68a;border-radius:12px;padding:12px;display:flex;flex-direction:column;gap:8px">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px">
        <div><strong style="font-size:13px">${escapeHtml(d.device)}</strong><br><span style="font-size:11px;color:#8a8f98">${escapeHtml(d.id)} • ${escapeHtml(d.nama)}</span></div>
        <span class="badge-status ${escapeHtml(badgeClassForStatus(d.status))}" style="font-size:10px">${escapeHtml(displayStatus(d.status))}</span>
      </div>
      <div style="font-size:11px;color:#374151">📝 ${escapeHtml(d.keluhan)}</div>
      <div style="display:flex;gap:6px;align-items:center">
        <select onchange="assignTeknisi('${escapeHtml(d.id)}', this.value)" style="flex:1;padding:7px 8px;border-radius:8px;border:1px solid #fde68a;background:#fffbeb;font-size:12px;font-weight:600;color:#92400e">${optsHtml}</select>
        <button class="btn btn-dark small" style="padding:7px 10px;font-size:11px" onclick="openDetail('${escapeHtml(d.id)}')">Detail</button>
      </div>
      <div style="display:flex;gap:6px;align-items:center;justify-content:space-between">
        <button class="btn btn-ghost small" style="padding:5px 7px;background:#dcfce7;border-color:#bbf7d0;color:#166534;display:inline-grid;place-items:center;width:30px;height:30px;border-radius:8px" onclick="openWhatsApp('${escapeHtml(d.wa)}','${escapeHtml(d.nama)}','${escapeHtml(d.device)}','${escapeHtml(d.id)}','${escapeHtml(d.keluhan)}')" title="WA">${WA_ICON}</button>
        <span style="font-size:10px;color:#8a8f98">${escapeHtml(formatTanggal(d.date))} • ${deadlineBadge(d)}</span>
      </div>
    </div>`;
  }).join('') + (menunggu.length>12 ? `<div style="grid-column:1/-1;text-align:center;font-size:11px;color:#92400e;padding:6px">+ ${menunggu.length-12} device lainnya di tabel bawah</div>` : '');
}
function renderSemuaService(){
  const tbody=document.querySelector('#tableSemua tbody');
  if(!tbody) return;
  const q = (document.getElementById('searchSemua')?.value || '').toLowerCase();
  const fRaw = document.getElementById('filterStatusSemua')?.value || '';
  // normalisasi filter legacy Selesai -> Service Sukses
  const f = fRaw==='Selesai' ? 'Service Sukses' : fRaw;
  let filtered=[...data];
  if(q) filtered=filtered.filter(d=> (d.id+d.nama+d.device+d.wa+d.keluhan+d.penerima).toLowerCase().includes(q));
  if(f) {
    // Service Sukses harus match Selesai legacy juga
    if(f==='Service Sukses') filtered=filtered.filter(d=> d.status==='Service Sukses' || d.status==='Selesai');
    else filtered=filtered.filter(d=>d.status===f);
  }
  filtered = filtered.filter(passesDeadlineFilter);
  // update blok menunggu teknisi (selalu dari data full, bukan filtered, agar warning tetap)
  renderMenungguTeknisiBlock();
  tbody.innerHTML = filtered.map(d=>{
    const isMenunggu = d.teknisi==='Menunggu Teknisi' || !d.teknisi || d.teknisi==='-';
    const baseOpts = ['Menunggu Teknisi', ...availableTechs.map(t=>t.username)];
    if(d.teknisi && !baseOpts.includes(d.teknisi)) baseOpts.push(d.teknisi);
    const uniqOpts = [...new Set(baseOpts)];
    const optionsHtml = uniqOpts.map(name=>{
      const sel = name===d.teknisi ? 'selected' : '';
      const tech = availableTechs.find(t=>t.username===name);
      const label = tech ? `${name} (${tech.role})` : name;
      return `<option value="${escapeHtml(name)}" ${sel}>${escapeHtml(label)}</option>`;
    }).join('');
    const selectStyle = isMenunggu
      ? 'background:#fffbeb;border-color:#fde68a;color:#92400e;font-weight:600'
      : 'background:#fff;border-color:#ececec';
    const statusOpts = statusOptions();
    const statusOptionsHtml = statusOpts.map(s=>`<option value="${escapeHtml(s)}" ${s===d.status?'selected':''}>${escapeHtml(s)}</option>`).join('');
    const statusStyle = (()=>{ const s=d.status; if(s==='Antri') return 'background:#fffbeb;border-color:#fde68a;color:#92400e'; if(s==='Menunggu Konfirmasi') return 'background:#fef9c3;border-color:#fde68a;color:#854d0e'; if(s==='Dikerjakan') return 'background:#eff6ff;border-color:#bfdbfe;color:#1d4ed8'; if(s==='Menunggu Sparepart') return 'background:#fef3c7;border-color:#fde68a;color:#92400e'; if(s==='Selesai'||s==='Service Sukses'||s==='Bisa Diambil') return 'background:#ecfdf5;border-color:#a7f3d0;color:#065f46'; if(s==='Sudah Diambil') return 'background:#f3f4f6;border-color:#e5e7eb;color:#374151'; if(s==='Service Failed') return 'background:#fef2f2;border-color:#fecaca;color:#991b1b'; if(s==='Garansi') return 'background:#f5f3ff;border-color:#ddd6fe;color:#5b21b6'; if(s==='Dibatalkan') return 'background:#f3f4f6;border-color:#e5e7eb;color:#6b7280'; return 'background:#fff;border-color:#ececec'; })();
    return `
    <tr data-invoice="${escapeHtml(d.id)}" style="${d.is_overdue?'background:#fffafa':''}">
      <td><strong style="font-size:11px">${escapeHtml(d.id)}</strong><br><span style="color:#8a8f98;font-size:10px">${escapeHtml(formatTanggal(d.date))}</span></td>
      <td><div class="avatar-cell" style="gap:6px"><img src="https://i.pravatar.cc/100?u=${escapeHtml(d.wa)}" style="width:26px;height:26px"><div><strong style="font-size:11px">${escapeHtml(d.nama)}</strong><br><span style="color:#8a8f98;font-size:10px">${escapeHtml(d.device)}</span></div></div></td>
      <td style="font-size:11px">${escapeHtml(d.keluhan)}<br><span style="font-size:10px">${deadlineBadge(d)}</span></td>
      <td>
        <select onchange="assignTeknisi('${escapeHtml(d.id)}', this.value)" title="Ubah teknisi" style="padding:5px 6px;border-radius:8px;border:1px solid #ececec;font-size:11px;min-width:120px;${selectStyle}">
          ${optionsHtml}
        </select>
      </td>
      <td>
        ${(()=>{ 
          const isEmpty = !d.penerima || d.penerima==='-' || d.penerima==='';
          const baseP = [...availableTechs.map(t=>t.username)];
          if(d.penerima && d.penerima!=='-' && !baseP.includes(d.penerima)) baseP.push(d.penerima);
          const uniqP = [...new Set(baseP.filter(Boolean))];
          const optsP = uniqP.map(name=>{
            const m = availableTechs.find(t=>t.username===name);
            const label = m ? `${name} (${m.role})` : name;
            return `<option value="${escapeHtml(name)}" ${name===d.penerima?'selected':''}>${escapeHtml(label)}</option>`;
          }).join('');
          const styleP = isEmpty ? 'background:#fffbeb;border-color:#fde68a;color:#92400e' : 'background:#f0f9ff;border-color:#bae6fd;color:#0369a1';
          const placeholder = isEmpty ? `<option value="" disabled selected>Pilih</option>` : '';
          return `<select onchange="assignPenerima('${escapeHtml(d.id)}', this.value)" title="Ubah penerima" style="padding:5px 6px;border-radius:8px;border:1px solid #ececec;font-size:11px;min-width:110px;font-weight:600;${styleP}">${placeholder}${optsP}</select>`;
        })()}
      </td>
      <td style="text-align:center"><button class="btn btn-ghost small" style="padding:5px 7px;font-size:11px;background:#dcfce7;border-color:#bbf7d0;color:#166534;display:inline-grid;place-items:center;width:32px;height:32px;border-radius:8px" onclick="openWhatsApp('${escapeHtml(d.wa)}','${escapeHtml(d.nama)}','${escapeHtml(d.device)}','${escapeHtml(d.id)}','${escapeHtml(d.keluhan)}')" title="Direct WhatsApp ke ${escapeHtml(d.wa)} (pakai WA yang login di PC)">${WA_ICON}</button></td>
      <td style="font-size:11px">Rp ${Number(d.biaya).toLocaleString('id-ID')}</td>
      <td>
        <select onchange="updateStatus('${escapeHtml(d.id)}', this.value)" title="Ubah status" style="padding:5px 6px;border-radius:8px;border:1px solid #ececec;font-size:11px;min-width:110px;font-weight:600;${statusStyle}">
          ${statusOptionsHtml}
        </select>
      </td>
      <td><button class="btn btn-ghost small" style="padding:4px 6px;font-size:11px" onclick="toggleInlineDetail('${escapeHtml(d.id)}')" id="btn-detail-${escapeHtml(d.id)}">Detail</button></td>
    </tr>
  `;
  }).join('') || `<tr><td colspan="9" style="text-align:center;padding:14px;color:#8a8f98;font-size:11px">Tidak ada data</td></tr>`;
  const el=document.getElementById('semuaCount'); if(el) el.textContent = filtered.length + ' service';
}
function toggleInlineDetail(invoice){
  const existing = document.getElementById(`inline-detail-${invoice}`);
  const btn = document.getElementById(`btn-detail-${invoice}`);
  // tutup jika sudah terbuka
  if(existing){
    existing.remove();
    if(btn) btn.textContent = '▼ Detail';
    return;
  }
  // tutup detail lain (hanya satu inline terbuka)
  document.querySelectorAll('.inline-detail-row').forEach(r=>r.remove());
  document.querySelectorAll('[id^="btn-detail-"]').forEach(b=>{ if(b.id!==`btn-detail-${invoice}`) b.textContent='▼ Detail'; });
  const d = data.find(x=>x.id===invoice);
  if(!d) return;
  const dlBadge = deadlineBadge(d);
  const row = document.querySelector(`tr[data-invoice="${invoice}"]`);
  if(!row) return;
  const kelengkapan = Array.isArray(d.kelengkapan) ? d.kelengkapan.join(', ') : (d.kelengkapan||'-');
  const detailHtml = `
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;font-size:13px">
      <div style="display:grid;gap:6px">
        <div><strong>Device:</strong> ${escapeHtml(d.device)}</div>
        <div><strong>Pelanggan:</strong> ${escapeHtml(d.nama)} • ${escapeHtml(d.wa)}</div>
        <div><strong>Keluhan:</strong> ${escapeHtml(d.keluhan)}</div>
        <div><strong>Kelengkapan:</strong> ${escapeHtml(kelengkapan||'-')}</div>
      </div>
      <div style="display:grid;gap:6px">
        <div><strong>Teknisi:</strong> <span class="meta-pill">👨‍🔧 ${escapeHtml(d.teknisi)}</span></div>
        <div><strong>Penerima:</strong> <span class="meta-pill" style="background:#f0f9ff;border-color:#bae6fd;color:#0369a1">📥 ${escapeHtml(d.penerima||'-')}</span></div>
        <div><strong>Biaya:</strong> Rp ${Number(d.biaya).toLocaleString('id-ID')}</div>
      <div><strong>Status:</strong> <span class="badge-status ${escapeHtml(badgeClassForStatus(d.status))}">${escapeHtml(displayStatus(d.status))}</span></div>
      </div>
      <div style="display:grid;gap:6px">
        <div><strong>Tgl Masuk:</strong> ${escapeHtml(formatTanggal(d.date))}</div>
        <div><strong>Estimasi Selesai:</strong> ${escapeHtml(formatTanggal(d.estimasi_selesai))} <span style="font-size:11px;color:#8a8f98">(jatuh tempo)</span></div>
        <div><strong>Deadline:</strong> ${dlBadge} ${d.is_overdue?'<span style="background:#ef4444;color:#fff;padding:2px 6px;border-radius:8px;font-size:10px">OVERDUE</span>':''}</div>
        <div style="font-size:11px;color:#6b7280">Invoice ${escapeHtml(d.id)} • ${escapeHtml(d.deadline_type||'harian')}</div>
      </div>
    </div>
    <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap">
      <button class="btn small" style="background:#dcfce7;border:1px solid #bbf7d0;color:#166534" onclick="openWhatsApp('${escapeHtml(d.wa)}','${escapeHtml(d.nama)}','${escapeHtml(d.device)}','${escapeHtml(d.id)}','${escapeHtml(d.keluhan)}')">${WA_ICON} Direct WhatsApp</button>
      <button class="btn btn-dark small" onclick="window.print()">🖨 Cetak Nota</button>
      <button class="btn btn-ghost small" onclick="openDetail('${escapeHtml(d.id)}')">↗ Modal Lengkap</button>
      <button class="btn btn-ghost small" onclick="toggleInlineDetail('${escapeHtml(d.id)}')">▲ Tutup</button>
    </div>
  `;
  const tr = document.createElement('tr');
  tr.id = `inline-detail-${invoice}`;
  tr.className = 'inline-detail-row';
  tr.innerHTML = `<td colspan="9" style="background:#f9fafb;padding:16px;border:1px solid #ececec;border-top:3px solid #111;animation:fade .18s"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px"><strong style="font-size:13px">📋 Detail Inline — ${escapeHtml(d.id)}</strong><button class="btn btn-ghost small" onclick="toggleInlineDetail('${escapeHtml(d.id)}')">✕ Tutup</button></div>${detailHtml}</td>`;
  row.insertAdjacentElement('afterend', tr);
  tr.scrollIntoView({behavior:'smooth', block:'nearest'});
  if(btn) btn.textContent = '▲ Tutup';
}
function renderStatusView(targetId, statusName){
  const wrap=document.getElementById(targetId);
  if(!wrap) return;
  // Jika tab Bisa Diambil, tampilkan status 'Service Sukses' + 'Bisa Diambil' (Selesai legacy juga)
  let filtered;
  if(statusName==='Bisa Diambil'){
    filtered = data.filter(d=> ['Bisa Diambil','Service Sukses','Selesai'].includes(d.status)).filter(passesDeadlineFilter);
  } else if(statusName==='Service Sukses'){
    filtered = data.filter(d=> ['Service Sukses','Selesai'].includes(d.status)).filter(passesDeadlineFilter);
  } else {
    filtered = data.filter(d=>d.status===statusName).filter(passesDeadlineFilter);
  }
  const opts = statusOptions().map(s=>`<option>${s}</option>`).join('');
  wrap.innerHTML = filtered.map(d=>`
    <div class="service-card" style="${d.is_overdue?'border-color:#fecaca;background:#fffafa':''}">
      <div class="service-card-head"><div><h4>${escapeHtml(d.device)}</h4><p>${escapeHtml(d.id)} • ${escapeHtml(d.nama)}</p></div><span class="badge-status ${escapeHtml(badgeClassForStatus(d.status))}">${escapeHtml(displayStatus(d.status))}</span></div>
      <p>📝 ${escapeHtml(d.keluhan)}</p>
      <div class="service-meta"><span class="meta-pill">👨‍🔧 ${escapeHtml(d.teknisi)}</span><span class="meta-pill">💰 Rp ${Number(d.biaya).toLocaleString('id-ID')}</span>${deadlineBadge(d)}</div>
      <div class="card-actions"><select onchange="updateStatus('${escapeHtml(d.id)}', this.value)" style="flex:1;padding:8px;border-radius:10px;border:1px solid #ececec;font-size:12px"><option disabled selected>Ubah status</option>${opts}</select><button class="btn btn-ghost small" onclick="openDetail('${escapeHtml(d.id)}')">Detail</button></div>
    </div>
  `).join('') || `<div style="grid-column:1/-1;text-align:center;padding:40px;color:#8a8f98">Belum ada service dengan status <strong>${statusName==='Bisa Diambil' ? 'Service Sukses / Bisa Diambil' : escapeHtml(displayStatus(statusName))}</strong></div>`;
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
    renderAll(); renderSemuaService(); showToast(`Status ${id} → ${newStatus}`);
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
      if(item){ item.deadline_type=newType; item.deadline=computeDeadline(item.date, newType); item.sisa_hari=computeSisa(item.deadline); item.is_overdue = item.sisa_hari<0 && !['Selesai','Service Sukses','Sudah Diambil','Dibatalkan','Service Failed'].includes(item.status); saveLocal(); }
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
  const penerima=document.getElementById('f-penerima')?.value || null;
  if(!nama||!wa||!device||!keluhan) return showToast('Lengkapi field wajib!');
  if(!estimasi) return showToast('Estimasi Selesai wajib diisi — deadline mengikuti estimasi');
  if(!penerima) return showToast('Penerima wajib dipilih');

  const payload = {
    nama, wa,
    device: device,
    imei: imei || null,
    keluhan,
    kelengkapan: [...selectedKelengkapan],
    biaya,
    teknisi,
    penerima,
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
  // after reset, set default teknisi menunggu & repopulate penerima
  const teknisiSel = document.getElementById('f-teknisi');
  if(teknisiSel) teknisiSel.value = 'Menunggu Teknisi';
  // reset penerima ke placeholder & reload anggota
  const penerimaSel = document.getElementById('f-penerima');
  if(penerimaSel) penerimaSel.value = '';
  if(availableTechs.length) populateTeknisiSelect();
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
  const baseOpts = ['Menunggu Teknisi', ...availableTechs.map(t=>t.username)];
  if(d.teknisi && !baseOpts.includes(d.teknisi)) baseOpts.push(d.teknisi);
  const uniqOpts = [...new Set(baseOpts)];
  const teknisiOptions = uniqOpts.map(name=>{
    const tech = availableTechs.find(t=>t.username===name);
    const label = tech ? `${name} (${tech.role})` : name;
    return `<option value="${escapeHtml(name)}" ${name===d.teknisi?'selected':''}>${escapeHtml(label)}</option>`;
  }).join('');
  // penerima options
  const penerimaOpts = [...new Set(availableTechs.map(t=>t.username).concat(d.penerima && d.penerima!=='-' ? [d.penerima] : []))];
  const penerimaOptions = penerimaOpts.map(name=>{
    const m = availableTechs.find(t=>t.username===name);
    const label = m ? `${name} (${m.role})` : name;
    return `<option value="${escapeHtml(name)}" ${name===d.penerima?'selected':''}>${escapeHtml(label)}</option>`;
  }).join('');
  const hasPenerima = penerimaOpts.length>0;
  document.getElementById('modalContent').innerHTML=`
    <h3 style="margin-bottom:6px">${escapeHtml(d.device)}</h3>
    <p style="color:#8a8f98;font-size:13px;margin-bottom:14px">${escapeHtml(d.id)} • ${escapeHtml(formatTanggal(d.date))} • ${escapeHtml(d.deadline_type)} • deadline ${escapeHtml(formatTanggal(d.deadline))} ${d.estimasi_selesai? ' • estimasi '+escapeHtml(formatTanggal(d.estimasi_selesai)):''}</p>
    <div style="display:grid;gap:10px;font-size:13px">
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap"><strong>Pelanggan:</strong> ${escapeHtml(d.nama)} (${escapeHtml(d.wa)}) <button class="btn small" style="background:#dcfce7;border:1px solid #bbf7d0;color:#166534;padding:5px 10px" onclick="openWhatsApp('${escapeHtml(d.wa)}','${escapeHtml(d.nama)}','${escapeHtml(d.device)}','${escapeHtml(d.id)}','${escapeHtml(d.keluhan)}')">${WA_ICON} WA Direct</button></div>
      <div><strong>Keluhan:</strong> ${escapeHtml(d.keluhan)}</div>
      <div><strong>Kelengkapan:</strong> ${escapeHtml((d.kelengkapan||[]).join(', ')||'-')}</div>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap"><strong>Teknisi:</strong> <span class="meta-pill">${escapeHtml(d.teknisi)}</span>
        <select id="modalTeknisi" style="padding:6px 8px;border-radius:8px;border:1px solid #ececec;font-size:12px;min-width:160px">${teknisiOptions}</select>
        <button class="btn btn-ghost small" onclick="assignTeknisiFromModal('${escapeHtml(d.id)}')">Assign</button>
      </div>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap"><strong>Penerima:</strong> <span class="meta-pill">${escapeHtml(d.penerima||'-')}</span>
        <select id="modalPenerima" style="padding:6px 8px;border-radius:8px;border:1px solid #ececec;font-size:12px;min-width:160px">${hasPenerima? penerimaOptions : '<option value="">- Belum ada anggota -</option>'}</select>
        <button class="btn btn-ghost small" onclick="assignPenerimaFromModal('${escapeHtml(d.id)}')">Simpan</button>
      </div>
      <div><strong>Biaya:</strong> Rp ${Number(d.biaya).toLocaleString('id-ID')}</div>
      <div><strong>Status:</strong> <span class="badge-status ${escapeHtml(badgeClassForStatus(d.status))}">${escapeHtml(displayStatus(d.status))}</span></div>
      <div><strong>Estimasi Selesai:</strong> ${escapeHtml(formatTanggal(d.estimasi_selesai))} <span style="font-size:11px;color:#8a8f98">(jatuh tempo = estimasi)</span></div>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <input id="modalEstimasi" type="date" value="${escapeHtml(d.estimasi_selesai||'')}" style="padding:6px 8px;border-radius:8px;border:1px solid #ececec;font-size:12px">
        <button class="btn btn-ghost small" onclick="updateEstimasi('${escapeHtml(d.id)}')">Ubah Estimasi</button>
      </div>
      <div><strong>Deadline:</strong> ${dlBadge} ${d.is_overdue?'<span style="background:#ef4444;color:#fff;padding:2px 6px;border-radius:8px;font-size:10px">OVERDUE</span>':''} <span style="font-size:11px;color:#6b7280">otomatis mengikuti Estimasi Selesai</span></div>
    </div>
    <div style="margin-top:18px;display:flex;gap:10px">
      <button class="btn btn-dark" style="flex:1" onclick="window.print()">Cetak Nota</button>
      <button class="btn btn-ghost" style="flex:1" onclick="closeModal()">Tutup</button>
    </div>
  `;
  document.getElementById('modal').classList.add('show');
}
function assignTeknisiFromModal(invoice){
  const sel = document.getElementById('modalTeknisi');
  if(!sel) return;
  assignTeknisi(invoice, sel.value).then(()=>{ closeModal(); openDetail(invoice); });
}
function assignPenerimaFromModal(invoice){
  const sel = document.getElementById('modalPenerima');
  if(!sel || !sel.value) return showToast('Pilih penerima');
  assignPenerima(invoice, sel.value).then(()=>{ closeModal(); openDetail(invoice); });
}
async function assignPenerima(invoice, newPenerima){
  if(!invoice || !newPenerima) return;
  try{
    if(USE_API){
      await apiFetch(`/services/${invoice}`, {method:'PATCH', body: JSON.stringify({penerima: newPenerima})});
      await loadData();
    } else {
      const item=data.find(d=>d.id===invoice);
      if(item){ item.penerima=newPenerima; saveLocal(); }
    }
    renderAll(); renderSemuaService(); showToast(`📥 ${invoice} → penerima: ${newPenerima}`);
  }catch(e){ showToast('Gagal assign penerima: '+e.message); }
}
async function updateEstimasi(invoice){
  const inp = document.getElementById('modalEstimasi');
  if(!inp || !inp.value) return showToast('Pilih tanggal estimasi');
  const newDate = inp.value;
  try{
    if(USE_API){
      await apiFetch(`/services/${invoice}`, {method:'PATCH', body: JSON.stringify({estimasi_selesai: newDate})});
      await loadData();
    } else {
      const item=data.find(d=>d.id===invoice);
      if(item){ item.estimasi_selesai=newDate; item.deadline=newDate; item.deadline_type = (new Date(newDate)-new Date(item.date))/(86400000) <=3 ? 'harian':'mingguan'; item.sisa_hari=computeSisa(newDate); saveLocal(); }
    }
    renderAll(); renderSemuaService(); closeModal(); showToast(`📅 ${invoice} estimasi → ${newDate} (deadline mengikuti)`); updateDeadlinePreview();
  }catch(e){ showToast('Gagal ubah estimasi: '+e.message); }
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
window.openDetail=openDetail; window.toggleInlineDetail=toggleInlineDetail; window.closeModal=closeModal; window.updateStatus=updateStatus;
window.handleLogout=handleLogout; window.handleCustomerSubmit=handleCustomerSubmit;
window.renderSemuaService=renderSemuaService; window.renderStatusView=renderStatusView;
window.loadApprovalData=loadApprovalData; window.approveUser=approveUser; window.rejectUser=rejectUser;
window.refreshPendingBadge=refreshPendingBadge; window.handleNotifClick=handleNotifClick;
window.openEditUserModal=openEditUserModal; window.closeUserModal=closeUserModal; window.submitUserEdit=submitUserEdit;
window.toggleFreezeUser=toggleFreezeUser; window.deleteUser=deleteUser; window.filterAllUsers=filterAllUsers; window.renderAllUsers=renderAllUsers;
window.loadAvailableTechs=loadAvailableTechs; window.populateTeknisiSelect=populateTeknisiSelect; window.assignTeknisi=assignTeknisi; window.assignTeknisiFromModal=assignTeknisiFromModal;
window.assignPenerima=assignPenerima; window.assignPenerimaFromModal=assignPenerimaFromModal; window.updateEstimasi=updateEstimasi;
window.setDeadlineFilter=setDeadlineFilter; window.updateDeadline=updateDeadline; window.updateDeadlinePreview=updateDeadlinePreview;
window.hitungLama=hitungLama; window.formatTanggalImage=formatTanggalImage; window.cleanWA=cleanWA; window.openWhatsApp=openWhatsApp;
window.API_BASE=API_BASE;
window.renderHitsIndicators=renderHitsIndicators; window.getBrandFromDevice=getBrandFromDevice; window.getKeluhanCategory=getKeluhanCategory; window.renderMenungguTeknisiBlock=renderMenungguTeknisiBlock; window.badgeClassForStatus=badgeClassForStatus; window.displayStatus=displayStatus;
window.loadProfil=loadProfil; window.handleProfilUpdate=handleProfilUpdate; window.renderLaporanTeknisi=renderLaporanTeknisi; window.avatarUrlFor=avatarUrlFor;
window.loadInventory=loadInventory; window.saveInventory=saveInventory; window.renderSparepart=renderSparepart; window.updateSparepartField=updateSparepartField; window.saveSparepartRow=saveSparepartRow; window.deleteSparepart=deleteSparepart; window.handleSparepartAdd=handleSparepartAdd; window.openSpEditModal=openSpEditModal; window.closeSpEditModal=closeSpEditModal; window.submitSpEdit=submitSpEdit; window.resetSparepartDummy=resetSparepartDummy;
window.loadAlat=loadAlat; window.saveAlat=saveAlat; window.renderAlat=renderAlat; window.updateAlatField=updateAlatField; window.saveAlatRow=saveAlatRow; window.deleteAlat=deleteAlat; window.openAlatAddModal=openAlatAddModal; window.openAlatEditModal=openAlatEditModal; window.closeAlatModal=closeAlatModal; window.submitAlatEdit=submitAlatEdit; window.resetAlatDummy=resetAlatDummy; window.kondisiBadge=kondisiBadge;
window.loadSparepartUsage=loadSparepartUsage; window.saveSparepartUsage=saveSparepartUsage; window.pakaiSparepart=pakaiSparepart; window.sparepartSelectOptions=sparepartSelectOptions; window.filterSparepartSelect=filterSparepartSelect; window.filterSparepartInput=filterSparepartInput; window.showSparepartDropdown=showSparepartDropdown; window.selectSparepart=selectSparepart; window.suggestSparepart=suggestSparepart; window.openSparepartLog=openSparepartLog; window.renderUsedSpareparts=renderUsedSpareparts; window.getUsedCount=getUsedCount; window.normalizeMerk=normalizeMerk; window.inferMerkFromNama=inferMerkFromNama; window.merkBadgeStyle=merkBadgeStyle;
window.statGoMasuk=statGoMasuk; window.statGoProses=statGoProses; window.statGoSukses=statGoSukses; window.statGoPendapatan=statGoPendapatan; window.statGoOverdue=statGoOverdue; window.statGoToday=statGoToday; window.statGoHarian=statGoHarian; window.statGoMingguan=statGoMingguan;
