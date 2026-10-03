// Business Engine UI: settings, kas saya, buku kas, kuota, oper garansi
function _rp(n){ try{ return formatRupiah(Number(n)||0); }catch(e){ return 'Rp '+Number(n||0).toLocaleString('id-ID'); } }
function _esc(s){ try{ return escapeHtml(String(s??'')); }catch(e){ return String(s??''); } }

async function loadEngineSettings(){
  const card = document.getElementById('engineSettingsCard');
  const msg = document.getElementById('engineSettingsMsg');
  try{
    const role = (localStorage.getItem('role')||'').toLowerCase();
    const myRole = document.getElementById('waMyRole')?.textContent.toLowerCase() || '';
    const isOwner = role==='superadmin' || role==='owner' || myRole.includes('owner') || myRole.includes('superadmin');
    if(card) card.style.display = isOwner ? '' : 'none';
    if(!isOwner) return;
    const s = await apiFetch('/engine/settings');
    const set = (id,v)=>{ const el=document.getElementById(id); if(el) el.value=v??''; };
    set('eng-uang', s.uang_hadir); set('eng-jam', s.jam_masuk);
    set('eng-toleransi', s.toleransi_mnt); set('eng-kuota', s.kuota_ringan_per_berat);
    set('eng-senior', s.komisi_senior); set('eng-junior', s.komisi_junior);
    set('eng-cicil', s.cicilan_max_pct); set('eng-toleransi-rp', s.toleransi_junior_rp);
    if(msg){ msg.style.display='none'; }
  }catch(e){
    if(msg){ msg.style.display='block'; msg.style.color='#dc2626'; msg.textContent='Gagal: '+String(e.message).slice(0,150); }
  }
}
async function saveEngineSettings(){
  const msg = document.getElementById('engineSettingsMsg');
  const num = (id)=>{ const v=document.getElementById(id)?.value||''; const n=parseInt(String(v).replace(/\D/g,'')); return isNaN(n)?undefined:n; };
  const body = {};
  const uang=num('eng-uang'); if(uang!==undefined) body.uang_hadir=uang;
  const jam=document.getElementById('eng-jam')?.value.trim(); if(jam) body.jam_masuk=jam;
  const tol=document.getElementById('eng-toleransi')?.value; if(tol!==''&&tol!==undefined) body.toleransi_mnt=parseInt(tol);
  const kuota=document.getElementById('eng-kuota')?.value; if(kuota) body.kuota_ringan_per_berat=parseInt(kuota);
  const sen=document.getElementById('eng-senior')?.value; if(sen!=='') body.komisi_senior=parseInt(sen);
  const jun=document.getElementById('eng-junior')?.value; if(jun!=='') body.komisi_junior=parseInt(jun);
  const cic=document.getElementById('eng-cicil')?.value; if(cic) body.cicilan_max_pct=parseInt(cic);
  const trp=num('eng-toleransi-rp'); if(trp!==undefined) body.toleransi_junior_rp=trp;
  try{
    await apiFetch('/engine/settings', {method:'PUT', body: JSON.stringify(body)});
    showToast('✅ Aturan engine disimpan');
    if(msg){ msg.style.display='block'; msg.style.color='#059669'; msg.textContent='✅ Tersimpan '+new Date().toLocaleTimeString('id-ID'); }
  }catch(e){ showToast('Gagal: '+e.message); }
}

function setLapTekTab(t){
  // Guard: tab kas owner khusus owner/admin — teknisi pakai Kas Saya
  try{
    const isTek = (window.BOSAuth && window.BOSAuth.isTeknisi && window.BOSAuth.isTeknisi())
      || String(localStorage.getItem('role') || '').toLowerCase() === 'teknisi';
    if(t === 'kas' && isTek){
      t = 'performa';
      try{ showToast('⛔ Buku kas khusus owner — kamu pakai Kas Saya'); }catch(e){}
    }
  }catch(e){}
  document.querySelectorAll('[data-laptek]').forEach(b=>b.classList.toggle('active', b.dataset.laptek===t));
  document.getElementById('lapTekPerforma').style.display = t==='performa'?'':'none';
  document.getElementById('lapTekKas').style.display = t==='kas'?'':'none';
  if(t==='kas') renderKasTeknisi();
}
function kasRowHtml(l){
  const tipe = {komisi_cair:'💰 Komisi', allowance:'🕘 Hadir', potongan_cicilan:'✂️ Cicilan', refund_balik:'↩️ Refund dibalik', hutang_baru:'⚠️ Hutang', toleransi_toko:'🛡️ Toko'}[l.tipe]||l.tipe;
  return `<tr><td>${_esc(l.tanggal||'')}</td><td>${_esc(l.invoice||'-')}</td><td>${tipe}</td><td style="text-align:right;color:#059669;font-weight:700">${l.masuk?_rp(l.masuk):''}</td><td style="text-align:right;color:#dc2626">${l.keluar?_rp(l.keluar):''}</td><td style="font-size:11px">${_esc(l.ket||'')}</td></tr>`;
}
async function renderKasTeknisi(){
  const sel = document.getElementById('kasTeknisiSelect');
  const tbody = document.getElementById('tbodyKasTeknisi');
  try{
    // isi dropdown dari teknisi list
    if(sel && !sel.options.length){
      const techs = await apiFetch('/technicians');
      sel.innerHTML = techs.map(t=>`<option value="${t.id}">${_esc(t.nama)} (${_esc(t.level||'junior')})</option>`).join('');
    }
    if(!sel?.value) { if(tbody) tbody.innerHTML='<tr><td colspan="6" style="text-align:center">Belum ada teknisi</td></tr>'; return; }
    const j = await apiFetch(`/engine/kas/teknisi/${sel.value}`);
    document.getElementById('kasKomisi').textContent = _rp(j.komisi_cair);
    document.getElementById('kasKomisiSub').textContent = `${j.nama} (${j.level}) • potongan ${_rp(j.potongan||0)} • diterima ${_rp(j.netto ?? j.total_diterima)}`;
    document.getElementById('kasAllowance').textContent = _rp(j.allowance);
    document.getElementById('kasHutang').textContent = _rp(j.sisa_hutang);
    document.getElementById('kasPending').textContent = `${j.pending_count} pending • komisi bruto ${_rp(j.komisi_bruto ?? j.komisi_cair)}`;
    tbody.innerHTML = (j.riwayat||[]).map(kasRowHtml).join('') || '<tr><td colspan="6" style="text-align:center">Belum ada riwayat</td></tr>';
    // pending list (Part UP disembunyikan dulu sesuai request)
    const pendWrap = document.getElementById('kasPendingList');
    if(pendWrap){
      pendWrap.innerHTML = (j.pending||[]).map(p=>`
        <div style="display:flex;gap:8px;align-items:center;border:1px solid #fde68a;background:#fffbeb;border-radius:10px;padding:8px 10px;font-size:12px">
          <strong>${_esc(p.invoice)}</strong><span>${_esc(p.kategori)}</span>
          <span>Komisi ${_rp(p.komisi)} • ${_esc(p.status_service||'')}</span>
        </div>`).join('');
    }
  }catch(e){
    if(tbody) tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:#dc2626">Gagal: ${_esc(e.message).slice(0,150)}</td></tr>`;
  }
}
let _kasTab = 'toko';
function setKasTab(t){
  // Arus Toko khusus owner/admin/superadmin — teknisi pakai Kas Saya
  try{
    const isTek = (window.BOSAuth && window.BOSAuth.isTeknisi && window.BOSAuth.isTeknisi())
      || String(localStorage.getItem('role') || '').toLowerCase() === 'teknisi';
    if(t === 'toko' && isTek){
      t = 'saya';
      try{ showToast('⛔ Arus Toko khusus owner — kamu pakai Kas Saya'); }catch(e){}
    }
  }catch(e){}
  _kasTab = t;
  document.querySelectorAll('[data-kas]').forEach(b=>b.classList.toggle('active', b.dataset.kas===t));
  try{ document.getElementById('kasPanel-toko').style.display = t==='toko'?'':'none'; }catch(e){}
  try{ document.getElementById('kasPanel-saya').style.display = t==='saya'?'':'none'; }catch(e){}
  if(t==='toko') renderKasToko();
  else renderKasSaya();
}
function _kasTokoRow(tanggal, ref, tipe, masuk, keluar, ket){
  return `<tr><td style="white-space:nowrap">${_esc(tanggal||'-')}</td><td style="font-size:11px"><strong>${_esc(ref||'-')}</strong></td><td>${_esc(tipe||'')}</td><td style="text-align:right;color:#059669;font-weight:700">${masuk?_rp(masuk):''}</td><td style="text-align:right;color:#dc2626">${keluar?_rp(keluar):''}</td><td style="font-size:11px">${_esc(ket||'')}</td></tr>`;
}
async function renderKasToko(force){
  const tbody = document.getElementById('tbodyKasToko');
  const set = (id,v)=>{ const el=document.getElementById(id); if(el) el.textContent=v; };
  try{
    const isTek = (window.BOSAuth && window.BOSAuth.isTeknisi && window.BOSAuth.isTeknisi())
      || String(localStorage.getItem('role') || '').toLowerCase() === 'teknisi';
    if(isTek){ setKasTab('saya'); return; }
    // Selalu hitung ulang tiap dibuka (jangan cache) — struk/pengeluaran/refund baru langsung masuk.
    if(tbody) tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:16px;color:#8a8f98">Menghitung arus kas toko...</td></tr>';
    const SUKSES = ['Service Sukses','Sudah Diambil','Selesai'];
    const actDate = d => String(d.diambil_at || d.updated_at || d.date || '').slice(0,10);
    let services = [];
    try{ services = await apiFetch('/services?limit=500'); }catch(e){ services = []; }
    const cair = (Array.isArray(services)?services:[]).filter(d=>SUKSES.includes(d.status));
    let masukTotal = cair.reduce((s,d)=>s+(Number(d.biaya)||0),0);
    const rows = cair.map(d=>({t: actDate(d), ref: d.invoice||'-', tipe: '💰 Pendapatan cair', masuk: Number(d.biaya)||0, keluar: 0, ket: `${d.device||''} • ${d.teknisi||''} • ${d.metode_bayar||'Belum bayar'}`}));
    // Omzet barang/jasa kasir = masuk
    try{
      const sl = await apiFetch('/sales?limit=300');
      (Array.isArray(sl)?sl:[]).forEach(s=>{
        const n = Number(s.total)||0; if(n<=0) return; masukTotal += n;
        rows.push({t: String(s.tanggal||'').slice(0,10), ref: s.kode||('#'+s.id), tipe: '🛒 Penjualan', masuk: n, keluar: 0, ket: `${(s.items||[]).length} item • ${s.metode||''}${s.pelanggan?' • '+s.pelanggan:''}`});
      });
    }catch(e){}
    // Pemasukan manual (modal awal / tambahan modal / lain) = masuk
    let inManual = 0;
    try{
      const inc = await apiFetch('/finance/incomes');
      (Array.isArray(inc)?inc:[]).forEach(s=>{
        const n = Number(s.nominal)||0; if(n<=0) return; inManual += n; masukTotal += n;
        rows.push({t: String(s.tanggal||'').slice(0,10), ref: s.kategori||'Masuk', tipe: '📥 Pemasukan', masuk: n, keluar: 0, ket: `${s.sumber||''}${s.dibuat_oleh?' • '+s.dibuat_oleh:''}`});
      });
    }catch(e){}
    // Keluar ke teknisi: komisi + hadir (dari buku kas masing-masing)
    let techKeluar = 0;
    try{
      const techs = await apiFetch('/technicians');
      const list = Array.isArray(techs)?techs:[];
      for(const t of list){
        try{
          const j = await apiFetch(`/engine/kas/teknisi/${t.id}`);
          const nama = j.nama || t.nama || ('Teknisi '+t.id);
          techKeluar += (Number(j.komisi_cair)||0) + (Number(j.allowance)||0);
          (j.riwayat||[]).forEach(l=>{
            if((Number(l.masuk)||0) > 0) rows.push({t: String(l.tanggal||'').slice(0,10), ref: l.invoice||'-', tipe: (l.tipe==='allowance'?'🕘 Hadir ':'💰 Komisi ') + nama, masuk: 0, keluar: Number(l.masuk)||0, ket: l.ket||''});
          });
        }catch(e){}
      }
    }catch(e){}
    // Refund nominal = keluar (dari omzet + jadi pengeluaran)
    let refundKeluar = 0;
    try{
      const rf = await apiFetch('/finance/refunds');
      const rlist = Array.isArray(rf)?rf:(rf.rows||[]);
      rlist.forEach(r=>{
        const n = Number(r.nominal)||0; refundKeluar += n;
        rows.push({t: String(r.tanggal||'').slice(0,10), ref: r.kode||r.invoice||'-', tipe: '💸 Refund', masuk: 0, keluar: n, ket: `${r.invoice||''} • ${r.alasan||''}`});
      });
    }catch(e){}
    // Kecelakaan kerja: beban toko = keluar
    let celakaKeluar = 0;
    try{
      const ac = await apiFetch('/finance/accidents');
      const alist = Array.isArray(ac)?ac:(ac.rows||[]);
      alist.forEach(a=>{
        const n = Number(a.beban_toko)||0; if(n<=0) return; celakaKeluar += n;
        rows.push({t: String(a.tanggal||'').slice(0,10), ref: a.invoice||'-', tipe: '🛠 Beban toko', masuk: 0, keluar: n, ket: `${a.teknisi||''} • ${a.kronologi||''}`});
      });
    }catch(e){}
    // Pengeluaran operasional = keluar
    let outKeluar = 0;
    try{
      const ex = await apiFetch('/finance/expenses');
      const xlist = Array.isArray(ex)?ex:(ex.rows||[]);
      xlist.forEach(r=>{
        const n = Number(r.nominal)||0; if(n<=0) return; outKeluar += n;
        const KL = {B1:'Sparepart',B2:'Accessories',C1:'Gaji',C2:'Tempat',C3:'Internet',C4:'Harian',C5:'Marketing',C6:'Maintenance',D:'Aset'};
        rows.push({t: String(r.tanggal||'').slice(0,10), ref: KL[r.kategori]||r.kategori||'Keluar', tipe: '🧾 Pengeluaran', masuk: 0, keluar: n, ket: `${r.keperluan||''}${r.dibuat_oleh?' • '+r.dibuat_oleh:''}`});
      });
    }catch(e){}
    const keluarTotal = techKeluar + refundKeluar + celakaKeluar + outKeluar;
    set('kasTokoMasuk', _rp(masukTotal)); set('kasTokoMasukSub', cair.length + ' service cair + omzet barang + manual ' + _rp(inManual));
    set('kasTokoKeluar', _rp(keluarTotal)); set('kasTokoKeluarSub', `teknisi ${_rp(techKeluar)} • refund ${_rp(refundKeluar)} • toko ${_rp(celakaKeluar)} • keluar ${_rp(outKeluar)}`);
    set('kasTokoSisa', _rp(masukTotal - keluarTotal));
    rows.sort((a,b)=>String(b.t||'').localeCompare(String(a.t||'')));
    if(tbody){
      tbody.innerHTML = rows.slice(0,120).map(r=>_kasTokoRow(r.t, r.ref, r.tipe, r.masuk, r.keluar, r.ket)).join('') || '<tr><td colspan="6" style="text-align:center;padding:16px;color:#8a8f98">Belum ada transaksi</td></tr>';
      tbody.dataset.filled = '1';
    }
  }catch(e){
    if(tbody) tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:#dc2626">Gagal: ${_esc(e.message).slice(0,150)}</td></tr>`;
  }
}
async function renderKasSaya(){
  const tbody = document.getElementById('tbodyKasSaya');
  try{
    const j = await apiFetch('/engine/kas/saya');
    document.getElementById('kasSayaSub').textContent = `${j.nama} (${j.level}) • transparan`;
    document.getElementById('kasSayaLevel').textContent = `${j.level} • total ${_rp(j.netto ?? j.total_diterima)}`;
    // hari ini & bulan ini dari riwayat (hari lokal WIB, bukan UTC)
    const _d = new Date();
    const today = _d.getFullYear()+'-'+String(_d.getMonth()+1).padStart(2,'0')+'-'+String(_d.getDate()).padStart(2,'0');
    const ym = today.slice(0,7);
    const hari = (j.riwayat||[]).filter(r=>String(r.tanggal||'').slice(0,10)===today).reduce((s,r)=>s+(r.masuk||0),0);
    const bulan = (j.riwayat||[]).filter(r=>String(r.tanggal||'').slice(0,7)===ym).reduce((s,r)=>s+(r.masuk||0),0);
    document.getElementById('kasSayaHari').textContent = _rp(hari);
    document.getElementById('kasSayaBulan').textContent = _rp(bulan);
    document.getElementById('kasSayaHutang').textContent = _rp(j.sisa_hutang);
    document.getElementById('kasSayaPending').textContent = `${j.pending_count} pending • allowance ${_rp(j.allowance)}`;
    tbody.innerHTML = (j.riwayat||[]).map(kasRowHtml).join('') || '<tr><td colspan="6" style="text-align:center">Belum ada riwayat — selesaikan service & check-in tepat waktu</td></tr>';
    // kuota
    try{
      const q = await apiFetch('/engine/kuota/me');
      const el = document.getElementById('kasSayaKuota');
      if(el){
        if(q.sisa===null||q.sisa===undefined) el.textContent = `Level: ${q.level} — bebas ambil ringan.`;
        else el.textContent = `Kuota 2:1 hari ini — berat ${q.berat_hari_ini}, ringan ${q.ringan_hari_ini}/${q.kuota_max}, sisa ${q.sisa}. Reset 00:00.`;
      }
    }catch{}
  }catch(e){
    if(tbody) tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:#dc2626">Gagal: ${_esc(e.message).slice(0,150)}</td></tr>`;
  }
}
async function refreshKuotaInfo(){
  const el = document.getElementById('kuotaInfo');
  if(!el) return;
  const tek = document.getElementById('f-teknisi')?.value || '';
  if(!tek || tek==='Menunggu Teknisi'){ el.textContent=''; return; }
  try{
    // kuota milik sendiri hanya akurat jika teknisi login; untuk kasir tampilkan hint umum
    el.textContent = `Kuota 2:1 senior — pastikan ${tek} sudah ambil berat sebelum 2 ringan.`;
  }catch{ el.textContent=''; }
}
async function setPartUp(invoice){
  const v = prompt('Harga Part UP untuk '+invoice+' (Rp, dilihat teknisi)?');
  if(v===null) return;
  const n = parseInt(String(v).replace(/\D/g,''))||0;
  try{
    await apiFetch(`/engine/service/${invoice}/part`, {method:'PUT', body: JSON.stringify({harga_part_up: n})});
    showToast('✅ Part UP disimpan');
    renderKasTeknisi();
  }catch(e){ showToast('Gagal: '+e.message); }
}
async function operGaransi(invoice){
  const to = prompt('Oper garansi '+invoice+' ke teknisi siapa? (nama)');
  if(!to) return;
  try{
    const r = await apiFetch(`/engine/garansi/${invoice}/oper`, {method:'POST', body: JSON.stringify({to_teknisi: to})});
    showToast(`✅ Dioper ${r.dari} → ${r.ke}`);
    if(typeof loadData==='function') await loadData(true);
    if(typeof renderStatusView==='function'){ renderStatusView('kanbanGaransi','Garansi'); }
  }catch(e){ showToast('Gagal oper: '+e.message); }
}
// ---------- Catat pemasukan manual langsung dari Kas Toko (kasir/owner/admin) ----------
function kasInOpen(){
  try{
    const m = document.getElementById('kasInModal');
    if(!m) return;
    const t = document.getElementById('kasin-tanggal');
    if(t && !t.value){
      const d = new Date();
      t.value = d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
    }
    kasInPreview();
    m.classList.add('show');
    setTimeout(()=>document.getElementById('kasin-sumber')?.focus(), 100);
  }catch(e){}
}
function kasInClose(){
  try{ document.getElementById('kasInModal')?.classList.remove('show'); }catch(e){}
}
function kasInPreview(){
  try{
    const n = parseInt(document.getElementById('kasin-nominal')?.value)||0;
    const k = document.getElementById('kasin-kategori')?.value||'Modal Awal';
    const c = document.getElementById('kasin-sumber')?.value.trim()||'-';
    const info = document.getElementById('kasin-nominalInfo');
    if(info) info.textContent = _rp(n);
    const p = document.getElementById('kasin-preview');
    if(p) p.innerHTML = n>0 ? `Akan dicatat: <strong>${_esc(k)}</strong> — ${_esc(c)} sebesar <strong>${_rp(n)}</strong> → masuk Total Masuk Kas Toko.` : 'Isi sumber + nominal dulu.';
  }catch(e){}
}
async function kasInSave(e){
  if(e) e.preventDefault();
  try{
    const sumber = document.getElementById('kasin-sumber')?.value.trim()||'';
    const nominal = parseInt(document.getElementById('kasin-nominal')?.value)||0;
    const kategori = document.getElementById('kasin-kategori')?.value||'Modal Awal';
    const metode = document.getElementById('kasin-metode')?.value||'Tunai';
    const tanggal = document.getElementById('kasin-tanggal')?.value||'';
    const keterangan = document.getElementById('kasin-ket')?.value.trim()||'';
    if(!sumber){ (window.showToast||alert)('Sumber wajib diisi'); return; }
    if(nominal<=0){ (window.showToast||alert)('Nominal harus > 0'); return; }
    const body = {sumber, nominal, kategori, metode};
    if(tanggal) body.tanggal = tanggal;
    if(keterangan) body.keterangan = keterangan;
    await apiFetch('/finance/incomes', {method:'POST', body: JSON.stringify(body)});
    kasInClose();
    try{ document.getElementById('kasInForm')?.reset(); }catch(_){}
    (window.showToast||alert)(`✅ Pemasukan ${kategori} ${_rp(nominal)} tersimpan — masuk Kas Toko`);
    await renderKasToko(true);
  }catch(err){
    (window.showToast||alert)('Gagal simpan: '+(err.message||err));
  }
}
// ---------- Catat pengeluaran langsung dari Kas Toko (kasir/owner/admin) ----------
function kasOutOpen(){
  try{
    const m = document.getElementById('kasOutModal');
    if(!m) return;
    const t = document.getElementById('kasout-tanggal');
    if(t && !t.value){
      const d = new Date();
      t.value = d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
    }
    kasOutPreview();
    m.classList.add('show');
    setTimeout(()=>document.getElementById('kasout-keperluan')?.focus(), 100);
  }catch(e){}
}
function kasOutClose(){
  try{ document.getElementById('kasOutModal')?.classList.remove('show'); }catch(e){}
}
function kasOutPreview(){
  try{
    const n = parseInt(document.getElementById('kasout-nominal')?.value)||0;
    const k = document.getElementById('kasout-kategori')?.value||'C4';
    const c = document.getElementById('kasout-keperluan')?.value.trim()||'-';
    const LBL = {B1:'Belanja Sparepart (HPP)',B2:'Belanja Accessories (HPP)',C1:'Gaji & Upah',C2:'Tempat',C3:'Internet & Sistem',C4:'Operasional Harian',C5:'Marketing',C6:'Maintenance',D:'Aset/Investasi'};
    try{ document.getElementById('kasout-subWrap').style.display = k==='D' ? '' : 'none'; }catch(e){}
    try{
      document.getElementById('kasout-stokWrap').style.display = (k==='B1'||k==='B2') ? '' : 'none';
      if(k==='B1'||k==='B2') kasOutSpFill();
    }catch(e){}
    const info = document.getElementById('kasout-nominalInfo');
    if(info) info.textContent = _rp(n);
    const dest = (k==='B1'||k==='B2') ? 'HPP' : k==='D' ? 'Aset (bukan biaya bulan ini)' : 'Operasional';
    const p = document.getElementById('kasout-preview');
    if(p) p.innerHTML = n>0 ? `Akan dicatat: <strong>${_esc(LBL[k]||k)}</strong> — ${_esc(c)} sebesar <strong>${_rp(n)}</strong> → masuk <strong>${dest}</strong> + buku besar.` : 'Isi keperluan + nominal dulu.';
  }catch(e){}
}
let _kasOutSpFilled = false;
async function kasOutSpFill(){
  if(_kasOutSpFilled) return; _kasOutSpFilled = true;
  try{
    const sp = await apiFetch('/inventory/spareparts');
    const sel = document.getElementById('kasout-sp');
    (Array.isArray(sp)?sp:[]).slice(0,300).forEach(s=>{
      const o = document.createElement('option');
      o.value = s.id; o.textContent = `${s.nama||'-'} (stok ${s.stok ?? '?'})`;
      sel.appendChild(o);
    });
  }catch(e){ _kasOutSpFilled = false; }
}
async function kasOutSave(e){
  if(e) e.preventDefault();
  try{
    const keperluan = document.getElementById('kasout-keperluan')?.value.trim()||'';
    const nominal = parseInt(document.getElementById('kasout-nominal')?.value)||0;
    const kategori = document.getElementById('kasout-kategori')?.value||'C4';
    const metode = document.getElementById('kasout-metode')?.value||'Tunai';
    const tanggal = document.getElementById('kasout-tanggal')?.value||'';
    const keterangan = document.getElementById('kasout-ket')?.value.trim()||'';
    if(!keperluan){ (window.showToast||alert)('Keperluan wajib diisi'); return; }
    if(nominal<=0){ (window.showToast||alert)('Nominal harus > 0'); return; }
    const body = {keperluan, nominal, kategori, metode};
    if(kategori==='D') body.subkategori = document.getElementById('kasout-sub')?.value||'Aset';
    try{
      const spId = parseInt(document.getElementById('kasout-sp')?.value)||0;
      const spQty = parseInt(document.getElementById('kasout-spqty')?.value)||0;
      if((kategori==='B1'||kategori==='B2')&&spId&&spQty>0) body.tambah_stok = {sparepart_id: spId, qty: spQty};
    }catch(e){}
    if(tanggal) body.tanggal = tanggal;
    if(keterangan) body.keterangan = keterangan;
    await apiFetch('/finance/expenses', {method:'POST', body: JSON.stringify(body)});
    kasOutClose();
    try{ document.getElementById('kasOutForm')?.reset(); }catch(_){}
    (window.showToast||alert)(`✅ Pengeluaran ${kategori} ${_rp(nominal)} tersimpan — masuk Kas Toko`);
    await renderKasToko(true);
  }catch(err){
    (window.showToast||alert)('Gagal simpan: '+(err.message||err));
  }
}
// hook ke switchView lama
(function(){
  const orig = window.switchView;
  window.switchView = function(view, clearSearch){
    if(orig) orig(view, clearSearch);
    try{
      const titles = {'kas-saya':['Kas Toko','Riwayat transaksi uang keseluruhan + sisa kas']};
      if(titles[view]){ document.getElementById('page-title').textContent=titles[view][0]; document.getElementById('page-subtitle').textContent=titles[view][1]; }
      if(view==='pengaturan'){ loadEngineSettings(); }
      if(view==='laporan-teknisi'){ /* tab kas butuh list */ }
      if(view==='kas-saya'){
        try{
          const isTek = (window.BOSAuth && window.BOSAuth.isTeknisi && window.BOSAuth.isTeknisi())
            || String(localStorage.getItem('role') || '').toLowerCase() === 'teknisi';
          document.querySelectorAll('[data-kas="toko"]').forEach(b=>{ b.style.display = isTek ? 'none' : ''; });
          setKasTab(isTek ? 'saya' : (_kasTab || 'toko'));
        }catch(e){ renderKasSaya(); }
      }
    }catch(e){}
  };
})();
