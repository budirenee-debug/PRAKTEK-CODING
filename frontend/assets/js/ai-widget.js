// AI widget Fase 1+ — chat laporan read-only multi-model, kanan bawah.
// Pakai apiFetch global (script.js) bila ada, fallback ke fetch sendiri.
(function () {
  const QUICK = ["Omset hari ini?", "Stok menipis apa?", "Service telat apa?", "Performa teknisi?"];
  const MODEL_KEY = "ai_model";
  let panel, msgs, form, input, sendBtn, fab, dot, modelSel;

  function apiBase() {
    if (typeof API_BASE !== "undefined" && API_BASE) return API_BASE;
    const host = location.hostname;
    if (host === "localhost" || host === "127.0.0.1") return "http://127.0.0.1:8000/api";
    return location.origin + "/api";
  }
  async function call(path, opts) {
    if (typeof apiFetch === "function") return apiFetch(path, opts);
    const token = localStorage.getItem("access_token");
    const url = apiBase() + path;
    const res = await fetch(url, {
      ...opts,
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: "Bearer " + token } : {}), ...((opts && opts.headers) || {}) },
    });
    if (!res.ok) throw new Error("HTTP " + res.status);
    return res.json();
  }
  function curModel() {
    try { return localStorage.getItem(MODEL_KEY) || ""; } catch (e) { return ""; }
  }
  function bubble(text, cls, meta) {
    const d = document.createElement("div");
    d.className = "ai-bubble " + cls;
    d.textContent = text;
    msgs.appendChild(d);
    if (meta) {
      const m = document.createElement("div");
      m.className = "ai-meta";
      m.style.alignSelf = cls === "ai-user" ? "flex-end" : "flex-start";
      m.textContent = meta;
      msgs.appendChild(m);
    }
    msgs.scrollTop = msgs.scrollHeight;
  }
  async function ask(q) {
    const query = (q || "").trim();
    if (!query || sendBtn.disabled) return;
    const model = (modelSel && modelSel.value) || curModel() || undefined;
    bubble(query, "ai-user");
    input.value = "";
    sendBtn.disabled = true;
    const typing = document.createElement("div");
    typing.className = "ai-typing";
    typing.textContent = "Ngetik...";
    msgs.appendChild(typing);
    msgs.scrollTop = msgs.scrollHeight;
    try {
      const body = { q: query };
      if (model) body.model = model;
      const r = await call("/ai/ask", { method: "POST", body: JSON.stringify(body) });
      typing.remove();
      const src = String(r.source || "");
      const via = src.startsWith("llm") ? "AI" : "ringkas";
      const mdl = r.model || model || "";
      bubble(r.answer || "(kosong)", "ai-ai", via + " • " + mdl + " • " + (r.intents || []).join(",") + " • " + (r.latency_ms || 0) + "ms");
    } catch (e) {
      typing.remove();
      bubble("Gagal tanya: " + e.message + " (cek login / backend).", "ai-ai", "error");
    } finally {
      sendBtn.disabled = false;
      input.focus();
    }
  }
  async function loadModels() {
    // Dropdown model: dari backend, tanpa bocorkan key.
    let def = "", list = [];
    try {
      const r = await call("/ai/models");
      def = r.default || "ollama";
      list = r.models || [];
    } catch (e) {
      list = [{ id: "ollama", label: "Ollama lokal", configured: true, free: true }];
      def = "ollama";
    }
    const saved = curModel();
    const active = list.some((m) => m.id === saved) ? saved : def;
    try { localStorage.setItem(MODEL_KEY, active); } catch (e) {}
    modelSel.innerHTML = "";
    list.forEach((m) => {
      const o = document.createElement("option");
      o.value = m.id;
      const badge = !m.configured ? " 🔑" : (m.free ? "" : " 💳");
      o.textContent = m.label + badge;
      if (!m.configured) o.title = m.hint || "Butuh API key di backend/.env";
      modelSel.appendChild(o);
    });
    modelSel.value = active;
    checkHealth();
  }
  async function checkHealth() {
    try {
      const m = (modelSel && modelSel.value) || curModel() || "ollama";
      const h = await call("/ai/health?model=" + encodeURIComponent(m));
      const ok = !!(h && h.ok && (h.reachable || h.configured));
      dot.className = "dot " + (ok ? "on" : "off");
      dot.title = ok ? (m + " online") : (m + " offline — mode ringkas. " + ((h && h.hint) || ""));
    } catch (e) {
      dot.className = "dot off";
      dot.title = "Belum login / backend mati";
    }
  }
  function build() {
    if (document.getElementById("aiFab")) return;
    fab = document.createElement("button");
    fab.id = "aiFab";
    fab.innerHTML = '<span class="dot" id="aiDot"></span>🤖 Tanya AI';
    dot = fab.querySelector("#aiDot");
    fab.onclick = () => { panel.classList.toggle("open"); if (panel.classList.contains("open")) input.focus(); };
    panel = document.createElement("div");
    panel.id = "aiPanel";
    panel.innerHTML =
      "<header>🤖 Bantu AI <select id='aiModel' title='Pilih model'></select><button id='aiClose'>×</button></header>" +
      "<div id='aiQuick'></div><div id='aiMsgs'></div>" +
      "<form id='aiForm'><input id='aiInput' placeholder='cth: omset hari ini?' maxlength='500' autocomplete='off'/><button type='submit' id='aiSend'>➤</button></form>";
    document.body.appendChild(fab);
    document.body.appendChild(panel);
    msgs = panel.querySelector("#aiMsgs");
    form = panel.querySelector("#aiForm");
    input = panel.querySelector("#aiInput");
    sendBtn = panel.querySelector("#aiSend");
    modelSel = panel.querySelector("#aiModel");
    modelSel.onchange = () => {
      try { localStorage.setItem(MODEL_KEY, modelSel.value); } catch (e) {}
      checkHealth();
    };
    const quick = panel.querySelector("#aiQuick");
    QUICK.forEach((q) => {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = q;
      b.onclick = () => ask(q);
      quick.appendChild(b);
    });
    panel.querySelector("#aiClose").onclick = () => panel.classList.remove("open");
    form.onsubmit = (e) => { e.preventDefault(); ask(input.value); };
    bubble("Halo bro 👋 Pilih model di atas (Ollama gratis / Bunny / Muse), terus tanya omset, teknisi, stok, status.", "ai-ai", "read-only • multi-model");
    loadModels();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", build);
  else build();
})();
