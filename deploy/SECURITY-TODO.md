# TODO Keamanan Server (diingatkan saat projek sudah jauh)

- [ ] Matikan login password SSH di `brserver` (khusus key) — saat ini masih
      menerima password, dan akses luar sudah kebuka via `ssh.reneepsl.my.id`.
      Cara: `PasswordAuthentication no` di `/etc/ssh/sshd_config` + `sudo systemctl reload ssh`.
      Prasyarat: pastikan key auth jalan dari semua perangkat yang butuh
      (`ssh brserver-luar` tanpa password) SEBELUM dimatikan, biar tidak kekunci.
- [ ] Pertimbangkan fail2ban / ganti port SSH internal bila perlu.

Status: DITUNDA atas permintaan owner (2026-10-07) — kerjakan saat projek stabil.
