// BOS embed mode — dipakai index.html & owner.html saat dimuat di dalam app.html.
// Standalone (dibuka langsung): tidak ada perubahan.
// Di dalam iframe app.html: sidebar + overlay bawaan disembunyikan (navigasi ikut shell),
// hamburger bawaan disembunyikan (pakai tombol shell), topbar isi (search/tombol) tetap jalan.
(function () {
  'use strict';
  try {
    var inFrame = false;
    try { inFrame = window.self !== window.top; } catch (e) { inFrame = true; }
    var forceEmbed = false;
    try { forceEmbed = /(?:\?|&)embed=1(?:&|$)/.test(location.search); } catch (e) {}
    if (!inFrame && !forceEmbed) return;
    document.documentElement.classList.add('is-embed');
    var css = '.is-embed aside.sidebar{display:none!important}'
      + '.is-embed .sidebar-overlay{display:none!important}'
      + '.is-embed header.topbar .hamburger{display:none!important}'
      + '.is-embed .app{display:block!important}'
      + '.is-embed main.main{margin-left:0!important}';
    var st = document.createElement('style');
    st.setAttribute('data-bos-embed', '1');
    st.appendChild(document.createTextNode(css));
    (document.head || document.documentElement).appendChild(st);
  } catch (e) {}
})();
