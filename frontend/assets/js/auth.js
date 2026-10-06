// BOS Auth — single source of truth untuk routing role.
// Dipakai login.html, index.html, dev.html. Jangan duplikasi logika di file lain.
(function (global) {
  'use strict';

  function resolveApiBase() {
    try {
      const stored = localStorage.getItem('API_BASE');
      if (stored) return stored;
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

  function requireTokenOrRedirect() {
    if (!getToken()) { goLoginReplace(); return false; }
    return true;
  }

  // Simpan hasil login ke localStorage dengan bentuk konsisten.
  function saveLogin(data) {
    try {
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
      ['access_token', 'username', 'role', 'nama', 'foto', 'bos_stores', 'active_store_id']
        .forEach(function (k) { localStorage.removeItem(k); });
    } catch (e) {}
    if (!silent) goLoginReplace();
  }

  // Validasi sesi ke backend. 401 -> token mati, tendang ke login.
  // 403 "belum jadi anggota" -> kembalikan {noStore:true} agar UI bisa kasih pesan.
  async function validateSession() {
    const token = getToken();
    if (!token) return { ok: false, reason: 'no-token' };
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
    saveLogin: saveLogin,
    landingFor: landingFor,
    redirectAfterLogin: redirectAfterLogin,
    logout: logout,
    validateSession: validateSession
  };
})(window);
