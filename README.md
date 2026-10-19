# Portal RT 09 / RW 14 - Sistem Informasi Kependudukan & Kas Paguyuban

Aplikasi Web Manajemen RT lengkap berbasis **Flask (Python)**, **Database SQL (SQLite + SQLAlchemy)**, dan antarmuka modern bernuansa Dark Indigo dengan **Tailwind CSS**.

Tampilan antarmuka dan data statistik awal dirancang presisi sesuai dengan referensi dashboard:
- **Total Kas**: Rp 1.215.000
- **Pemasukan**: Rp 1.215.000
- **Pengeluaran**: Rp 0
- **Status**: Aktif
- **Total Warga**: 51 orang
- **Iuran Lunas**: 81
- **Belum Lunas**: 110
- **Menunggu Konfirmasi**: 13

---

## Fitur Utama

1. **Dashboard**
   - Ringkasan statistik realtime: Total Kas, Pemasukan, Pengeluaran, Status Aktif.
   - Kotak **Pengumuman RT** resmi dari pengurus.
   - Kotak **Ringkasan RT**: Total Warga, Iuran Lunas, Belum Lunas, Menunggu Konfirmasi, dan progress bar kepatuhan iuran.
   - Shortcut aksi cepat: Bayar Iuran, Ajukan Surat, Lapor Masalah, Pinjam Aset.

2. **Data Warga (Privasi & Hak Akses: OWN View & Edit)**
   - **Sebagai Warga**:
     - **OWN View**: Warga yang login hanya dapat melihat profil pribadi dan anggota keluarga terdaftar dalam satu Kartu Keluarga (KK) miliknya. Akses ke data kependudukan warga lain diblokir demi privasi.
     - **OWN Edit**: Warga dapat memperbarui data dirinya secara mandiri (No. HP/WhatsApp, Email, Pekerjaan, Alamat, Status Perkawinan, dll.) langsung dari halaman profil. NIK dan No. KK dikunci untuk menjaga integritas data resmi.
   - **Sebagai Admin / Pengurus / Pejabat**:
     - Akses penuh untuk melihat seluruh 51 warga terdaftar, pencarian, filter, tambah warga baru, edit, hapus, dan export data CSV.

3. **Smart Login Warga (Nama + Blok No. Rumah)**
   - Warga dapat masuk ke portal tanpa perlu menghafal username teknis yang rumit.
   - Cukup gunakan kombinasi **bagian nama mana saja** dan **blok nomor rumah**:
     - *Contoh*: Warga bernama **Ahmad Budiman Sujatmiko** yang tinggal di rumah **Blok G nomor 65** dapat login dengan salah satu dari username berikut:
       - `AhmadG65`
       - `BudimanG65`
       - `SujatmikoG65`
       - Atau dengan spasi/garis miring: `Ahmad G65`, `Budiman G/65`
       - Serta variasi huruf kecil: `ahmadg65`, `budimang65`
     - *Contoh*: Warga bernama **Budi Santoso** di **Blok B3 No. 12** dapat login dengan `BudiB312`, `SantosoB312`, atau `warga1`.
   - Kata sandi standar awal warga: `warga123` (dapat diubah kapan saja di menu *Ganti Password*).

4. **Buku Besar Rumah & Keterhunian (Dual-Key Property Ledger)**
   - **Solusi Pergantian Warga Kontrak vs Pemilik Rumah**:
     - Aturan RT: Warga yang tinggal dan memperoleh manfaat pelayanan RT adalah penanggung jawab iuran bulanan.
     - Sistem memisahkan entitas **Fisik Rumah** (`Rumah`), **Pemilik Sah** (`pemilik_id`), dan **Penghuni Aktif** (`penghuni_aktif_id`).
     - **Buku Besar Rumah Abadi**: Seluruh riwayat transaksi iuran terkait langsung dengan `rumah_id`. Ketika penyewa berganti, buku besar rumah tidak terpecah dan dapat diaudit secara utuh oleh Ketua RT, Bendahara, maupun pemilik rumah.
     - **Fitur Serah Terima Keterhunian (`/rumah/serah-terima/<id>`)**:
       - Deteksi otomatis tunggakan penghuni lama sebelum kunci/deposit diserahkan.
       - Pilihan alur: *Ganti Pengontrak Baru*, *Kembali Dihuni Pemilik*, atau *Kosongkan Unit*.
       - Pencatatan Berita Acara Serah Terima (meter listrik, meter air, kunci).
       - Menjaga linimasa keterhunian (`RiwayatKeterhunian`) secara kronologis.

5. **Iuran Warga**
   - **Tampilan Warga**: Memantau riwayat tagihan pribadi, status (Lunas / Belum Lunas / Menunggu Konfirmasi).
   - **Pembayaran Mandiri**: Modal scan **QRIS** resmi dan info rekening BCA, form unggah bukti transfer.
   - **Tampilan Admin / Bendahara**: Kelola seluruh tagihan warga, verifikasi bukti transfer menjadi Lunas, catat penerimaan tunai, dan tombol *Generate Tagihan Periode Baru*.

6. **Transaksi Kas RT**
   - Laporan keuangan arus kas (*Cash Flow*): Pemasukan dan Pengeluaran.
   - Form pencatatan penerimaan selain iuran bulanan (Donasi, Sumbangan, Kas Awal, Sewa Aset).
   - Form pencatatan pengeluaran (Operasional RT, Kebersihan, Keamanan/Satpam, Lampu Jalan, Kegiatan Warga).
   - Filter tanggal & jenis transaksi.
   - **Cetak Laporan Keuangan**: Format cetak resmi kop surat RT 09 dengan tanda tangan Ketua RT dan Bendahara.

7. **Persuratan**
   - Pengelolaan administrasi surat pengantar warga dengan nomor surat otomatis.
   - Template surat siap pakai:
     1. Surat Pengantar RT (Pembuatan/Pembaruan KTP / KK)
     2. Surat Keterangan Domisili
     3. Surat Keterangan Usaha (SKU)
     4. Surat Keterangan Tidak Mampu (SKTM)
     5. Surat Keterangan Kematian
     6. Surat Keterangan Kelahiran
     7. Surat Izin Keramaian / Acara
   - Alur persetujuan pengurus: Diajukan $\rightarrow$ Diproses $\rightarrow$ Disetujui / Ditolak.
   - **Cetak Surat Resmi**: Kop surat resmi RT 09 / RW 14 Kelurahan Mojosarirejo, data warga pemohon, tanda tangan Ketua RT, cap digital, dan barcode.

8. **Pengumuman**
   - Saluran komunikasi resmi pengurus kepada warga.
   - Kategori pengumuman: Penting, Info Warga, Kegiatan, Iuran, Keamanan.
   - Prioritas Tinggi (Badge merah berkedip) & Biasa.

9. **Inventaris Aset RT**
   - **Pengadaan**: Pencatatan aset baru milik RT (Sound System, Tenda, Kursi, Mesin Rumput, dll).
   - **Peminjaman**: Formulir peminjaman aset oleh warga dengan batas tanggal kembali dan status pengembalian.
   - **Disposal**: Berita acara penghapusan aset rusak berat/hilang dengan pencatatan nilai residu penjualan rombeng ke kas.

10. **Pelaporan & Pengaduan Warga**
    - Warga dapat melaporkan masalah lingkungan (lampu PJU mati, got tersumbat, keamanan, jalan rusak).
    - Unggah foto bukti kejadian.
    - Timeline penanganan dan form respon / tindak lanjut oleh pengurus RT.

11. **Pengaturan Sistem**
    - **Identitas RT**: Pengaturan nama RT, RW, Kelurahan, Kecamatan, Kota, Kode Pos, Nama Ketua RT, dan nominal iuran standar.
    - **Notifikasi API**: Konfigurasi endpoint WhatsApp Gateway (Fonnte/Wablas) & template pesan otomatis.
    - **Pengaturan QRIS & Rekening**: Nama merchant, NMID, rekening bank tujuan kas, dan petunjuk transfer.
    - **Integrasi Payment Gateway Mayar.id & Webhook QRIS**:
      - Pembuatan QRIS dinamis dan payment checkout Mayar secara instan (`/iuran/mayar/create/<id>`).
      - Endpoint Webhook otomatis (`/api/webhook/mayar`) untuk event `payment.received`.
      - Verifikasi instan: saat warga membayar via QRIS, status tagihan otomatis menjadi `Lunas` dan langsung tercatat ke `TransaksiKas` tanpa perlu verifikasi manual.
      - Fitur keamanan token secret query/header untuk mencegah webhook palsu.
      - Panel pengujian simulasi webhook 1-klik langsung dari dashboard Superadmin tanpa perlu ngrok.
    - **Import & Export**:
      - Unduh template CSV resmi.
      - Upload massal data warga dari CSV.
      - Upload massal data tagihan iuran dari CSV.
    - **Manajemen Pengguna, Tipe & Peran (Role)**:
      - **Tipe Pengguna (User Type)**:
        - `Superadmin`: Akun teknis sistem, **bukan warga** (`warga_id = None`), tidak memiliki iuran bulanan pribadi.
        - `Warga Pemilik`: Warga pemegang hak milik rumah di RT 09.
        - `Warga Kontrak`: Warga pengontrak/sewa yang menempati unit rumah di RT 09.
      - **Peran (Role)**:
        - `Superadmin`: Konfigurasi sistem, manajemen user, backup & restore.
        - `Ketua RT`: Pengesahan/tanda tangan persuratan, disposisi inventaris, pengumuman resmi.
        - `Pengurus`: Operasional keuangan kas, verifikasi iuran, pendataan warga dan inventaris.
        - `Warga`: Akses pribadi (OWN view/edit, pembayaran iuran, pengajuan surat, pelaporan).

12. **Ganti Password & Logout**
    - Fitur keamanan bagi setiap pengguna untuk mengubah kata sandi akunnya.
    - Logout aman dari sesi portal.

13. **Format Dokumen Resmi, Kuitansi & Surat Edaran**
    - **Kuitansi Iuran Resmi**:
      - Dilengkapi nomor registrasi kuitansi unik (`KWT/RT09/YYYY/MM/XXXX`).
      - Konversi otomatis nilai nominal uang menjadi huruf terbilang bahasa Indonesia (contoh: *Lima Belas Ribu Rupiah*).
      - Kode QR verifikasi digital keabsahan dokumen paguyuban RT.
      - Tanda tangan ganda digital: Bendahara Paguyuban & Mengetahui Ketua RT.
      - Desain responsif slip cetak A4 yang ramah printer (`@media print`).
    - **Surat Resmi RT (Pengantar / Domisili / Usaha)**:
      - Kop surat resmi paguyuban RT dinamis yang sinkron dengan menu Pengaturan Identitas.
      - QR barcode verifikasi dokumen digital dan cap stempel resmi RT.
    - **Surat Edaran RT**:
      - Cetak pengumuman resmi warga menjadi lembar Surat Edaran formal bertanda tangan Ketua RT untuk edaran fisik / papan pengumuman.
    - **Format Laporan Kas Keuangan RT**:
      - Kop surat resmi, tabel rincian mutasi kas masuk/keluar, ringkasan saldo akhir.
      - Status audit digital dan pengesahan dua tanda tangan (Bendahara & Ketua RT).

14. **Progressive Web App (PWA) & Offline Capability**
    - Memenuhi standar PWA modern dengan `manifest.json` dan `sw.js` (Service Worker).
    - Dapat di-*install* langsung di layar beranda ponsel (Android / iOS) atau desktop (Chrome / Edge) layaknya aplikasi native.
    - Caching aset cerdas (App Shell) dan halaman fallback saat jaringan offline.

15. **Style Dinamis Dark & Light Mode**
    - Tombol *toggle* pergantian tema satu-klik di bar navigasi atas.
    - Palet warna Dark Slate elegan dan Light Slate bersih berdaya kontras tinggi.
    - Preferensi tema disimpan secara persisten di `localStorage` tanpa efek kedip (*flash-free*).

---

## Matriks Akun Demo, Tipe Pengguna & Peran

| Peran (Role) | Tipe Pengguna (User Type) | Username | Password | Warga Terkait / Status |
|---|---|---|---|---|
| **Superadmin** | `Superadmin` | `admin` | `admin123` | **Bukan Warga** (Akun Teknis Sistem, `warga_id=None`) |
| **Ketua RT** | `Warga Pemilik` | `ketua_rt` / `pejabat` / `BambangA101` | `pejabat123` | H. Bambang Sutrisno (Pemilik Rumah A1/01 & G/65) |
| **Pengurus** | `Warga Pemilik` | `pengurus` / `AhmadA205` | `pengurus123` | Ahmad Fauzi, S.E. (Bendahara, Rumah A2/05) |
| **Warga** | `Warga Pemilik` | `warga1` / `BudiB312` | `warga123` | Budi Santoso (Pemilik Rumah B3/12) |
| **Warga** | `Warga Kontrak` | `AhmadG65` / `BudimanG65` / `SujatmikoG65` | `warga123` | Ahmad Budiman Sujatmiko (Pengontrak Rumah G/65) |

*Tersedia tombol satu-klik ("Akses Cepat Demo Akun") di halaman Login untuk kemudahan pengujian langsung.*

---

## Cara Menjalankan Aplikasi

1. Pastikan dependensi Python telah terpasang:
   ```bash
   pip install flask flask-sqlalchemy werkzeug openpyxl
   ```

2. Kompilasi Tailwind CSS (Produksi):
   Aplikasi menggunakan **Tailwind CLI** lokal (bukan CDN) yang menghasilkan bundle CSS produksi yang ramping dan termodifikasi di `static/css/tailwind.min.css`:
   ```bash
   # Build bundle CSS produksi (minified)
   npm run build:css

   # Atau watch mode untuk mendeteksi perubahan template saat pengembangan
   npm run watch:css
   ```

3. Jalankan aplikasi:
   ```bash
   python app.py
   ```

4. Buka browser pada alamat:
   ```
   http://127.0.0.1:5000
   ```

