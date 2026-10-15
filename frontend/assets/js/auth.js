// BOS Auth — single source of truth untuk routing role.
// Dipakai login.html, index.html, dev.html. Jangan duplikasi logika di file lain.
(function (global) {
  'use strict';

  function sanitizeApiBase(v) {
    if (!v || typeof v !== 'string') return null;
    v = v.trim();
    if (!/^https?:\/\/.+\/api\/?$/.test(v)) return null;
    if (/[<>"'`\s\\]/.test(v)) return null;
    // hanya izinkan localhost / 127.0.0.1 / domain prod + trycloudflare (anti-racun localStorage)
    if (!/(localhost|127\.0\.0\.1|reneepsl\.my\.id|trycloudflare\.com)/.test(v)) return null;
    return v.replace(/\/+$/, '');
  }

  function resolveApiBase() {
    try {
      const clean = sanitizeApiBase(localStorage.getItem('API_BASE'));
      if (clean) return clean;
      else if (localStorage.getItem('API_BASE')) localStorage.removeItem('API_BASE');
    } catch (e) {}
    const proto = location.protocol;
    const host = location.hostname;
    if (proto === 'file:') return 'http://127.0.0.1:8000/api';
    if (host === 'localhost' || host === '127.0.0.1') return 'http://127.0.0.1:8000/api';
    if (!host || host === 'null') return 'http://127.0.0.1:8000/api';
    return location.origin + '/api';
  }

  const API = resolveApiBase();

  function getToken() {
    try { return localStorage.getItem('access_token'); } catch (e) { return null; }
  }

  function getGlobalRole() {
    try { return (localStorage.getItem('role') || '').trim().toLowerCase(); } catch (e) { return ''; }
  }

  function getStores() {
    try {
      const arr = JSON.parse(localStorage.getItem('bos_stores') || '[]');
      return Array.isArray(arr) ? arr : [];
    } catch (e) { return []; }
  }

  function getActiveStoreId() {
    try {
      const v = parseInt(localStorage.getItem('active_store_id') || '', 10);
      return isNaN(v) ? null : v;
    } catch (e) { return null; }
  }

  // Peran aktif = peran di toko aktif (role_saya dari /stores, atau role dari /auth/login).
  // Global role hanya fallback. Selalu lowercase.
  function myActiveRole() {
    const g = getGlobalRole();
    if (g === 'superadmin') return 'superadmin';
    try {
      const stores = getStores();
      const active = getActiveStoreId();
      const cur = stores.find(function (s) { return s.id === active; });
      if (cur) {
        const r = (cur.role_saya || cur.role || '').trim().toLowerCase();
        if (r) return r;
      }
    } catch (e) {}
    return g;
  }

  function isTeknisi() { return myActiveRole() === 'teknisi'; }
  function isKasir() { return myActiveRole() === 'kasir'; }
  function canManage() { return ['superadmin', 'owner', 'admin'].includes(myActiveRole()); }
  function canSeeFinance() { return ['superadmin', 'owner', 'admin'].includes(myActiveRole()); }

  function goLoginReplace() {
    try { location.replace('login.html'); } catch (e) { location.href = 'login.html'; }
  }

  // Batas sesi keras: 2 jam sejak login. Selaras dengan
  // backend ACCESS_TOKEN_EXPIRE_MINUTES=120. Unlock layar kunci via password
  // dihitung login ulang (memperbarui login_at).
  var SESSION_MAX_MS = 2 * 60 * 60 * 1000;

  function getLoginAt() {
    try {
      const v = parseInt(localStorage.getItem('login_at') || '0', 10);
      return isNaN(v) ? 0 : v;
    } catch (e) { return 0; }
  }

  function isSessionExpired() {
    try {
      const at = getLoginAt();
      if (!at) return false; // token lama sebelum ada login_at: andalkan exp JWT saja
      return (Date.now() - at) >= SESSION_MAX_MS;
    } catch (e) { return false; }
  }

  function isExpired(token) {
    try {
      const parts = String(token).split('.');
      if (parts.length !== 3) return false;
      const payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')));
      if (!payload.exp) return false;
      return (payload.exp * 1000) < (Date.now() + 10000);
    } catch (e) { return false; }
  }

  function requireTokenOrRedirect() {
    const t = getToken();
    if (!t || isExpired(t) || isSessionExpired()) {
      if (t && (isExpired(t) || isSessionExpired())) logout(true);
      else goLoginReplace();
      if (t && (isExpired(t) || isSessionExpired())) goLoginReplace();
      return false;
    }
    return true;
  }

  // Simpan hasil login ke localStorage dengan bentuk konsisten.
  function saveLogin(data) {
    try {
      localStorage.setItem('login_at', String(Date.now()));
      localStorage.setItem('access_token', data.access_token);
      localStorage.setItem('username', data.username || '');
      localStorage.setItem('role', (data.role || '').toLowerCase());
      localStorage.setItem('bos_stores', JSON.stringify(data.stores || []));
      if (data.primary_store_id) {
        localStorage.setItem('active_store_id', String(data.primary_store_id));
      } else {
        localStorage.removeItem('active_store_id');
      }
    } catch (e) {}
  }

  // Target landing per role:
  // index.html = dashboard toko (pintu utama; Owner Space via menu untuk owner/admin).
  // app.html tetap bisa dibuka manual sebagai shell unified (iframe index/owner).
  function landingFor(role) {
    return 'index.html';
  }

  function redirectAfterLogin(data) {
    saveLogin(data);
    const target = landingFor(data.role);
    setTimeout(function () {
      try { location.replace(target); } catch (e) { location.href = target; }
    }, 600);
  }

  function logout(silent) {
    try {
      ['access_token', 'username', 'role', 'nama', 'foto', 'bos_stores', 'active_store_id', 'login_at']
        .forEach(function (k) { localStorage.removeItem(k); });
    } catch (e) {}
    if (!silent) goLoginReplace();
  }

  // Validasi sesi ke backend. 401 -> token mati, tendang ke login.
  // Cek sesi 2 jam dulu (hemat request): kedaluwarsa -> langsung tendang.
  // 403 "belum jadi anggota" -> kembalikan {noStore:true} agar UI bisa kasih pesan.
  async function validateSession() {
    const token = getToken();
    if (!token) return { ok: false, reason: 'no-token' };
    if (isExpired(token) || isSessionExpired()) {
      logout(true);
      return { ok: false, reason: 'expired' };
    }
    try {
      const res = await fetch(API + '/auth/me', {
        headers: { 'Authorization': 'Bearer ' + token }
      });
      if (res.status === 401) {
        logout(true);
        return { ok: false, reason: 'expired' };
      }
      if (!res.ok) return { ok: false, reason: 'http-' + res.status };
      return { ok: true, me: await res.json() };
    } catch (e) {
      return { ok: false, reason: 'offline' };
    }
  }

  global.BOSAuth = {
    API: API,
    getToken: getToken,
    getGlobalRole: getGlobalRole,
    getStores: getStores,
    getActiveStoreId: getActiveStoreId,
    myActiveRole: myActiveRole,
    isTeknisi: isTeknisi,
    isKasir: isKasir,
    canManage: canManage,
    canSeeFinance: canSeeFinance,
    goLoginReplace: goLoginReplace,
    requireTokenOrRedirect: requireTokenOrRedirect,
    isExpired: isExpired,
    isSessionExpired: isSessionExpired,
    getLoginAt: getLoginAt,
    SESSION_MAX_MS: SESSION_MAX_MS,
    saveLogin: saveLogin,
    landingFor: landingFor,
    redirectAfterLogin: redirectAfterLogin,
    logout: logout,
    validateSession: validateSession
  };
})(window);
