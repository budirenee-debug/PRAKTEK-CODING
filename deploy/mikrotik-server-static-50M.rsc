# Mikrotik - Server Ubuntu tanpa TP-Link (bypass hotspot + limit 50M/50M)
# Target: 192.168.148.10/22 GW 192.168.148.1, MAC 80:EE:73:51:8D:6E
# Cara pakai: Winbox -> New Terminal -> paste semua, Enter
# Aman di-run ulang (idempotent: hapus dulu yg lama dgn IP/nama yg sama)

/ip hotspot ip-binding remove [find address=192.168.148.10]
/ip hotspot ip-binding add address=192.168.148.10 mac-address=80:EE:73:51:8D:6E type=bypassed comment="server-tanpa-tplink"

/queue simple remove [find name=server-static]
/queue simple add name=server-static target=192.168.148.10/32 max-limit=50M/50M comment="limit server 50M" place-before=0

# ---- verifikasi (jalanin setelah add) ----
/ip hotspot ip-binding print where address=192.168.148.10
/queue simple print where name=server-static
/ip hotspot active print where address=192.168.148.10
