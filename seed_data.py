import os
import json
import random
import re
from datetime import datetime, date, timedelta
from werkzeug.security import generate_password_hash
from models import (
    db, User, Warga, Rumah, RiwayatKeterhunian, Iuran, TransaksiKas, Surat, 
    Pengumuman, Inventaris, PeminjamanInventaris, DisposalInventaris, 
    Laporan, Pengaturan
)

def seed_database():
    print("Initializing and seeding database with Rumah, Keterhunian & Smart Login...")
    
    # Clear existing database for clean upgrade if necessary
    db.drop_all()
    db.create_all()

    # 1. Seed Settings (Identitas RT, Notifikasi API, QRIS, Import)
    settings = [
        # Identitas RT
        ('nama_rt', 'RT 09', 'identitas', 'Nomor RT'),
        ('nama_rw', 'RW 14', 'identitas', 'Nomor RW'),
        ('kelurahan', 'Mojosarirejo', 'identitas', 'Nama Kelurahan'),
        ('kecamatan', 'Driyor', 'identitas', 'Nama Kecamatan'),
        ('kota', 'Gresik', 'identitas', 'Nama Kota / Kabupaten'),
        ('provinsi', 'Jawa Timur', 'identitas', 'Nama Provinsi'),
        ('kode_pos', '601', 'identitas', 'Kode Pos'),
        ('nama_ketua_rt', 'Rudi Susanto.ST', 'identitas', 'Nama Ketua RT'),
        ('no_hp_rt', '0812-3456-7890', 'identitas', 'Nomor HP/WA Pengurus RT'),
        ('iuran_bulanan', '15000', 'identitas', 'Nominal Iuran Bulanan Standar (Rp)'),
        
        # Notifikasi API (WhatsApp / Gateway)
        ('wa_gateway_provider', 'Fonnte / Wablas API', 'notifikasi', 'Provider WhatsApp Gateway'),
        ('wa_api_url', 'https://api.fonnte.com/send', 'notifikasi', 'URL Endpoint API Gateway'),
        ('wa_api_token', 'DEMO_RT09_SECRET_TOKEN_2026', 'notifikasi', 'API Key / Token Otentikasi'),
        ('notif_auto_send', '1', 'notifikasi', 'Kirim Notifikasi Otomatis (1: Aktif, 0: Nonaktif)'),
        ('template_tagihan', 'Halo Bapak/Ibu {nama}, kami menginformasikan tagihan iuran {rt_rw} untuk Rumah {no_rumah} periode {periode} sebesar Rp {jumlah} status {status}. Mohon melakukan pembayaran melalui Portal Warga atau transfer kas RT. Terima kasih.', 'notifikasi', 'Template Pesan Tagihan Iuran'),
        ('template_konfirmasi_lunas', 'Terima kasih Bapak/Ibu {nama}. Pembayaran iuran {rt_rw} Rumah {no_rumah} periode {periode} sebesar Rp {jumlah} telah diverifikasi dan LUNAS. Partisipasi Anda sangat berarti bagi kemajuan lingkungan kita.', 'notifikasi', 'Template Konfirmasi Pembayaran Lunas'),
        ('template_surat_selesai', 'Halo {nama}, pengajuan surat pengantar {jenis_surat} dengan nomor {nomor_surat} telah disetujui oleh Pengurus {rt_rw}. Silakan unduh atau cetak surat Anda melalui portal.', 'notifikasi', 'Template Pengajuan Surat Disetujui'),
        ('template_pelaporan_respon', 'Halo {nama}, laporan pengaduan Anda mengenai "{judul}" telah direspon oleh Pengurus RT: Status [{status}]. Keterangan: {tanggapan}. Terima kasih atas kepedulian Anda.', 'notifikasi', 'Template Respon Pengaduan Warga'),

        # QRIS & Pembayaran Kas
        ('qris_merchant_name', 'KAS PAGUYUBAN RT 09 RW 14', 'qris', 'Nama Merchant QRIS'),
        ('qris_nmid', 'ID1020030040506', 'qris', 'National Merchant ID (NMID)'),
        ('qris_status', 'Aktif', 'qris', 'Status Penerimaan QRIS'),
        ('bank_nama', 'Bank Central Asia (BCA)', 'qris', 'Nama Bank Rekening Kas RT'),
        ('bank_rekening', '8830-1928-31', 'qris', 'Nomor Rekening Bank'),
        ('bank_atas_nama', 'PAGUYUBAN WARGA RT 09', 'qris', 'Nama Pemilik Rekening'),
        ('qris_instruksi', 'Scan QRIS di atas melalui m-Banking (BCA, Mandiri, BRI, BNI) atau e-Wallet (GoPay, OVO, Dana, ShopeePay). Simpan bukti transaksi dan unggah pada menu Iuran Warga.', 'qris', 'Petunjuk Pembayaran QRIS'),
        ('qris_payload', '00020101021126600016ID.CO.QRIS.WWW01189360052300000000010215ID10200300405060303UME51440014ID.CO.QRIS.WWW0215ID10200300405060303UME5204541153033605802ID5925KAS PAGUYUBAN RT 09 RW 146008DRIYOREJO61056117762200716KASRT09DRIYOREJO6304A1B2', 'qris', 'String Payload QRIS Standar EMVCo (NMID ID1020030040506)'),

        # Integrasi Payment Gateway Mayar.id
        ('mayar_is_active', '1', 'qris', 'Status Integrasi Mayar.id (1: Aktif, 0: Nonaktif)'),
        ('mayar_environment', 'sandbox', 'qris', 'Lingkungan Mayar (sandbox: api.mayar.io, production: api.mayar.id)'),
        ('mayar_api_key', '', 'qris', 'API Key Mayar.id (Bearer Token)'),
        ('mayar_webhook_token', 'mayar_rt09_secret_token_2026', 'qris', 'Secret Token Verifikasi Webhook Mayar'),

        # Import & Export
        ('import_delimiter', ',', 'import', 'Karakter Pemisah CSV'),
        ('import_auto_create_user', '1', 'import', 'Otomatis Buat Akun Warga Saat Import Warga Baru'),
    ]

    for key, val, kat, desk in settings:
        p = Pengaturan(kunci=key, nilai=val, kategori=kat, deskripsi=desk)
        db.session.add(p)

    # 2. Seed Warga (Total = 51 warga)
    warga_list = []
    
    # 1. Ketua RT (Pemilik Rumah A1/01 dan Pemilik Rumah G/65 yang dikontrakkan)
    warga_rt_ketua = Warga(
        nik='3175041205650001',
        no_kk='3175041205650000',
        nama='H. Bambang Sutrisno',
        jenis_kelamin='Laki-laki',
        tempat_lahir='Solo',
        tanggal_lahir=date(1965, 5, 12),
        agama='Islam',
        pekerjaan='Pensiunan BUMN',
        status_perkawinan='Kawin',
        status_keluarga='Kepala Keluarga',
        status_tinggal='Tetap',
        no_rumah='A1/01',
        alamat='Jl. De Naila Village Blok G No. 01, RT 09 / RW 14',
        rt_rw='09/14',
        no_hp='081234567890',
        email='ketua.rt09@portalrt.id',
        is_aktif=True
    )
    db.session.add(warga_rt_ketua)
    warga_list.append(warga_rt_ketua)

    # 2. Bendahara RT
    warga_bendahara = Warga(
        nik='3175042408780002',
        no_kk='3175042408780000',
        nama='Ahmad Fauzi, S.E.',
        jenis_kelamin='Laki-laki',
        tempat_lahir='Jakarta',
        tanggal_lahir=date(1978, 8, 24),
        agama='Islam',
        pekerjaan='Akuntan / Wiraswasta',
        status_perkawinan='Kawin',
        status_keluarga='Kepala Keluarga',
        status_tinggal='Tetap',
        no_rumah='A2/05',
        alamat='Jl. De Naila Village Blok G No. 05, RT 09 / RW 14',
        rt_rw='09/14',
        no_hp='081388992211',
        email='bendahara.rt09@portalrt.id',
        is_aktif=True
    )
    db.session.add(warga_bendahara)
    warga_list.append(warga_bendahara)

    # 3. Budi Santoso (Pemilik Rumah B3/12)
    warga_demo = Warga(
        nik='3175041503850003',
        no_kk='3175041503850000',
        nama='Budi Santoso',
        jenis_kelamin='Laki-laki',
        tempat_lahir='Semarang',
        tanggal_lahir=date(1985, 3, 15),
        agama='Islam',
        pekerjaan='Karyawan Swasta',
        status_perkawinan='Kawin',
        status_keluarga='Kepala Keluarga',
        status_tinggal='Tetap',
        no_rumah='B3/12',
        alamat='Jl. De Naila Village Blok G No. 12, RT 09 / RW 14',
        rt_rw='09/14',
        no_hp='085712345678',
        email='budi.santoso@gmail.com',
        is_aktif=True
    )
    db.session.add(warga_demo)
    warga_list.append(warga_demo)

    # 4. Ahmad Budiman Sujatmiko (Warga Kontrak di Blok G nomor 65 - Contoh dari User!)
    warga_ahmad = Warga(
        nik='3175041010920004',
        no_kk='3175041010920000',
        nama='Ahmad Budiman Sujatmiko',
        jenis_kelamin='Laki-laki',
        tempat_lahir='Yogyakarta',
        tanggal_lahir=date(1992, 10, 10),
        agama='Islam',
        pekerjaan='Arsitek / Konsultan',
        status_perkawinan='Kawin',
        status_keluarga='Kepala Keluarga',
        status_tinggal='Kontrak',
        no_rumah='G/65',
        alamat='Jl. Melati Blok G No. 65, RT 09 / RW 14',
        rt_rw='09/14',
        no_hp='081288776655',
        email='ahmad.budiman@gmail.com',
        is_aktif=True
    )
    db.session.add(warga_ahmad)
    warga_list.append(warga_ahmad)

    # Generate remaining 47 citizens to complete exactly 51 citizens!
    first_names_male = ['Joko', 'Agus', 'Hendra', 'Eko', 'Rudi', 'Dedi', 'Indra', 
                        'Bayu', 'Fajar', 'Surya', 'Wahyu', 'Tri', 'Gunawan', 'Hadi', 'Sutrisno', 'Doni', 'Rian',
                        'Aris', 'Yanto', 'Heru', 'Tono', 'Sigit', 'Prasetyo', 'Danang', 'Ilham', 'Firman']
    first_names_female = ['Siti', 'Dewi', 'Sri', 'Nur', 'Ratna', 'Lestari', 'Endang', 'Rina', 'Wati', 'Yuli',
                          'Maya', 'Dian', 'Fitri', 'Nita', 'Ayu', 'Rini', 'Tuti', 'Ika', 'Mega', 'Tia', 'Putri', 'Anggi']
    last_names = ['Kusuma', 'Saputra', 'Wijaya', 'Hidayat', 'Wibowo', 'Nugroho', 'Siregar', 
                  'Setiawan', 'Permana', 'Lubis', 'Kurniawan', 'Utomo', 'Susanto', 'Purnama', 'Firmansyah', 'Nasution']
    jobs = ['Karyawan Swasta', 'PNS', 'Wiraswasta', 'Guru', 'Dokter', 'Insinyur', 'Pedagang', 'TNI / POLRI', 'Pensiunan', 'Ibu Rumah Tangga']
    religions = ['Islam', 'Kristen Protestan', 'Katolik', 'Hindu', 'Buddha']

    random.seed(42)
    for i in range(5, 52):
        is_male = random.random() > 0.4
        fn = random.choice(first_names_male if is_male else first_names_female)
        ln = random.choice(last_names)
        full_name = f"{fn} {ln}"
        
        kk_num = 3175041000000000 + (i // 3) * 10
        nik_num = 3175040000000000 + i * 137 + 100000
        
        blok = chr(65 + (i % 4))
        no_rmh = f"{blok}{(i % 15) + 1}/{i:02d}"
        
        status_tinggal = 'Tetap' if (i % 5 != 0) else 'Kontrak'
        status_kel = 'Kepala Keluarga' if (i % 3 == 0) else ('Istri' if not is_male else 'Anak')
        status_kawin = 'Kawin' if status_kel in ['Kepala Keluarga', 'Istri'] else 'Belum Kawin'
        
        b_year = random.randint(1960, 2005)
        b_month = random.randint(1, 12)
        b_day = random.randint(1, 28)

        w = Warga(
            nik=str(nik_num),
            no_kk=str(kk_num),
            nama=full_name,
            jenis_kelamin='Laki-laki' if is_male else 'Perempuan',
            tempat_lahir=random.choice(['Jakarta', 'Bandung', 'Surabaya', 'Semarang', 'Yogyakarta', 'Medan', 'Bogor']),
            tanggal_lahir=date(b_year, b_month, b_day),
            agama=random.choice(religions),
            pekerjaan=random.choice(jobs),
            status_perkawinan=status_kawin,
            status_keluarga=status_kel,
            status_tinggal=status_tinggal,
            no_rumah=no_rmh,
            alamat=f"Jl. Melati Blok {blok} No. {i:02d}, RT 09 / RW 14",
            rt_rw='09/14',
            no_hp=f"08{random.randint(11, 99)}{random.randint(1000000, 9999999)}",
            email=f"{fn.lower()}.{ln.lower()}{i}@example.com",
            is_aktif=True
        )
        db.session.add(w)
        warga_list.append(w)

    db.session.flush()

    # 3. Seed Users (With User Type & Peran / Role)
    # User Type: Superadmin (Bukan Warga), Warga Pemilik, Warga Kontrak
    # Peran: Superadmin, Ketua RT, Pengurus, Warga
    users = [
        # Superadmin: Akun teknis sistem, BUKAN WARGA (warga_id=None)
        ('admin', 'admin123', 'Superadmin Portal RT', 'superadmin', 'superadmin', None, '081100009999'),
        # Ketua RT: Peran Ketua RT, Tipe Warga Pemilik (Rumah A1/01)
        ('ketua_rt', 'pejabat123', 'H. Bambang Sutrisno (Ketua RT)', 'ketua_rt', 'warga_pemilik', warga_rt_ketua.id, '081234567890'),
        ('pejabat', 'pejabat123', 'H. Bambang Sutrisno (Ketua RT)', 'ketua_rt', 'warga_pemilik', warga_rt_ketua.id, '081234567890'),
        # Pengurus: Peran Pengurus, Tipe Warga Pemilik (Rumah A2/05)
        ('pengurus', 'pengurus123', 'Ahmad Fauzi, S.E. (Bendahara)', 'pengurus', 'warga_pemilik', warga_bendahara.id, '081388992211'),
        # Warga: Peran Warga, Tipe Warga Pemilik (Rumah B3/12)
        ('warga1', 'warga123', 'Budi Santoso', 'warga', 'warga_pemilik', warga_demo.id, '085712345678'),
        # Warga: Peran Warga, Tipe Warga Kontrak (Mengontrak Rumah G/65)
        ('AhmadG65', 'warga123', 'Ahmad Budiman Sujatmiko', 'warga', 'warga_kontrak', warga_ahmad.id, '081288776655'),
    ]

    for uname, pwd, name, role, u_type, w_id, hp in users:
        u = User(
            username=uname,
            nama=name,
            role=role,
            user_type=u_type,
            warga_id=w_id,
            no_hp=hp,
            is_active=True
        )
        u.set_password(pwd)
        db.session.add(u)

    # Seed User accounts for all remaining citizens with smart primary usernames
    for w in warga_list:
        existing = User.query.filter_by(warga_id=w.id).first()
        if not existing:
            # Generate primary username: First word of name + cleaned house number
            name_part = re.sub(r'[^a-zA-Z0-9]', '', w.nama.split()[0])
            house_part = re.sub(r'[^a-zA-Z0-9]', '', w.no_rumah or 'RT09')
            default_uname = f"{name_part}{house_part}"
            # Ensure unique
            counter = 1
            final_uname = default_uname
            while User.query.filter_by(username=final_uname).first():
                final_uname = f"{default_uname}{counter}"
                counter += 1

            u_type = 'warga_kontrak' if w.status_tinggal == 'Kontrak' else 'warga_pemilik'
            u = User(
                username=final_uname,
                nama=w.nama,
                role='warga',
                user_type=u_type,
                warga_id=w.id,
                no_hp=w.no_hp,
                is_active=True
            )
            u.set_password('warga123')
            db.session.add(u)

    # 4. Seed Data Rumah & Status Keterhunian
    rumah_map = {}
    
    # Rumah G/65: Pemilik Pak RT (Bambang Sutrisno), Penghuni Aktif Pengontrak (Ahmad Budiman Sujatmiko)
    r_g65 = Rumah(
        no_rumah='G/65',
        blok='G',
        nomor='65',
        alamat='Jl. Melati Blok G No. 65, RT 09 / RW 14',
        pemilik_id=warga_rt_ketua.id,
        penghuni_aktif_id=warga_ahmad.id,
        status_huni='Dikontrakkan',
        tipe_penghuni='Pengontrak',
        tgl_mulai_sewa=date(2026, 2, 1),
        tgl_selesai_sewa=date(2027, 1, 31),
        catatan='Disewakan 1 tahun kepada Ahmad Budiman Sujatmiko. Pembayar iuran aktif adalah pengontrak.'
    )
    db.session.add(r_g65)
    rumah_map['G/65'] = r_g65

    # Log Riwayat Keterhunian untuk G/65
    log1 = RiwayatKeterhunian(
        rumah=r_g65,
        warga=warga_list[4], # Pengontrak sebelumnya (Rudi)
        tipe_penghuni='Pengontrak',
        tgl_mulai=date(2025, 1, 1),
        tgl_selesai=date(2026, 1, 31),
        is_aktif=False,
        status_tunggakan='Lunas',
        catatan_serah_terima='Sewa selesai 31 Januari 2026. Seluruh iuran dan rekening listrik lunas.'
    )
    log2 = RiwayatKeterhunian(
        rumah=r_g65,
        warga=warga_ahmad,
        tipe_penghuni='Pengontrak',
        tgl_mulai=date(2026, 2, 1),
        tgl_selesai=date(2027, 1, 31),
        is_aktif=True,
        status_tunggakan='Lunas',
        catatan_serah_terima='Mulai sewa baru 1 Februari 2026. Penanggung jawab iuran adalah Ahmad Budiman Sujatmiko.'
    )
    db.session.add_all([log1, log2])

    # Rumah B3/12 (Dihuni Pemilik Budi Santoso)
    r_b312 = Rumah(
        no_rumah='B3/12',
        blok='B3',
        nomor='12',
        alamat='Jl. De Naila Village Blok G No. 12, RT 09 / RW 14',
        pemilik_id=warga_demo.id,
        penghuni_aktif_id=warga_demo.id,
        status_huni='Dihuni Pemilik',
        tipe_penghuni='Pemilik',
        catatan='Ditempati sendiri oleh pemilik keluarga Budi Santoso.'
    )
    db.session.add(r_b312)
    rumah_map['B3/12'] = r_b312

    # Create Rumah records for all other citizens' homes
    for w in warga_list:
        nr = w.no_rumah
        if nr and nr not in rumah_map:
            parts = nr.split('/')
            b = parts[0] if len(parts) > 0 else 'A'
            n = parts[1] if len(parts) > 1 else '01'
            st_huni = 'Dikontrakkan' if w.status_tinggal == 'Kontrak' else 'Dihuni Pemilik'
            tipe_p = 'Pengontrak' if w.status_tinggal == 'Kontrak' else 'Pemilik'
            
            # If rented, owner is RT Ketua or Bendahara, resident is w
            pemilik_id = warga_rt_ketua.id if w.status_tinggal == 'Kontrak' else w.id
            r = Rumah(
                no_rumah=nr,
                blok=b,
                nomor=n,
                alamat=w.alamat,
                pemilik_id=pemilik_id,
                penghuni_aktif_id=w.id,
                status_huni=st_huni,
                tipe_penghuni=tipe_p,
                catatan='Data rumah paguyuban RT 09'
            )
            db.session.add(r)
            rumah_map[nr] = r

    db.session.flush()

    # 5. Seed Iuran (Exactly 81 Lunas, 110 Belum Lunas, 13 Menunggu Konfirmasi = 204 records)
    statuses = ['Lunas'] * 81 + ['Belum Lunas'] * 110 + ['Menunggu Konfirmasi'] * 13
    random.seed(99)
    random.shuffle(statuses)

    status_idx = 0
    nominal = 15000.0
    for bulan in [1, 2, 3, 4]:
        for w in warga_list:
            st = statuses[status_idx]
            status_idx += 1
            
            tgl_bayar = None
            metode = 'Tunai / Cash'
            verif_by = None
            verif_at = None
            bukti = None
            
            if st == 'Lunas':
                tgl_bayar = datetime(2026, bulan, random.randint(1, 20), random.randint(8, 17), random.randint(0, 59))
                metode = random.choice(['QRIS', 'Transfer Bank', 'Tunai / Cash'])
                verif_by = 'Ahmad Fauzi (Bendahara)'
                verif_at = tgl_bayar + timedelta(hours=random.randint(1, 5))
            elif st == 'Menunggu Konfirmasi':
                tgl_bayar = datetime(2026, 4, random.randint(10, 18), 14, 30)
                metode = random.choice(['QRIS', 'Transfer Bank'])
                bukti = 'bukti_transfer_sample.png'

            r_obj = rumah_map.get(w.no_rumah)
            tipe_p = 'Pengontrak' if w.status_tinggal == 'Kontrak' else 'Pemilik'

            iur = Iuran(
                rumah_id=r_obj.id if r_obj else None,
                warga_id=w.id,
                tipe_pembayar=tipe_p,
                periode_bulan=bulan,
                periode_tahun=2026,
                jumlah=nominal,
                status=st,
                metode_bayar=metode,
                tanggal_bayar=tgl_bayar,
                bukti_transfer=bukti,
                catatan=f"Iuran Rumah {w.no_rumah} Bulan {bulan}/2026 ({tipe_p}: {w.nama})",
                verified_by=verif_by,
                verified_at=verif_at
            )
            db.session.add(iur)

    # 6. Seed Transaksi Kas (Sum = Rp 1.215.000 pemasukan, Rp 0 pengeluaran)
    pemasukan_items = [
        ('TRX-2026-001', 'Pemasukan', 'Iuran Warga', 'Rekap Penerimaan Iuran Bulan Januari 2026', 450000.0, date(2026, 1, 31), 'Penerimaan iuran lunas Januari 30 warga'),
        ('TRX-2026-002', 'Pemasukan', 'Iuran Warga', 'Rekap Penerimaan Iuran Bulan Februari 2026', 420000.0, date(2026, 2, 28), 'Penerimaan iuran lunas Februari 28 warga'),
        ('TRX-2026-003', 'Pemasukan', 'Iuran Warga', 'Rekap Penerimaan Iuran Bulan Maret 2026', 345000.0, date(2026, 3, 31), 'Penerimaan iuran lunas Maret 23 warga'),
    ]
    for kode, jenis, kat, judul, jml, tgl, ket in pemasukan_items:
        tk = TransaksiKas(
            kode_transaksi=kode,
            jenis=jenis,
            kategori=kat,
            judul=judul,
            jumlah=jml,
            tanggal=tgl,
            keterangan=ket,
            created_by='Bendahara RT 09'
        )
        db.session.add(tk)

    # 7. Seed Pengumuman RT
    p1 = Pengumuman(
        judul='Pengumuman Penting: Penggunaan Fitur Pelaporan di Portal Warga RT 09',
        konten='Halo Warga RT 09, Kami informasikan bahwa kini portal warga RT 09 telah dilengkapi dengan fitur pelaporan yang memudahkan Bapak/Ibu untuk menyampaikan berbagai laporan terkait lingkungan dan kebutuhan warga. Berikut cara menggunakan fitur pelaporan: Masuk ke portal warga RT 09 melalui alamat resmi. Pilih menu Pelaporan di navigasi utama. Isi formulir laporan dengan lengkap dan jelas, termasuk jenis laporan dan deskripsi masalah. Kirim laporan, dan pengurus RT akan segera menindaklanjuti sesuai kebutuhan. Fitur ini bertujuan untuk meningkatkan komunikasi dan respons cepat terhadap permasalahan di lingkungan kita. Mohon gunakan fitur ini dengan bijak dan sesuai kebutuhan. Terima kasih atas partisipasi aktif Bapak/Ibu dalam menjaga kenyamanan dan keamanan lingkungan RT 09. Salam hormat, Pengurus RT 09 / RW 14',
        kategori='Penting',
        prioritas='Tinggi',
        tanggal=date(2026, 4, 15),
        is_aktif=True,
        author='Pengurus RT 09 / RW 14'
    )
    p2 = Pengumuman(
        judul='Info Warga: Kebersihan dan Keamanan Lingkungan',
        konten='Halo Bapak/Ibu Warga RT 09, Semoga hari ini menyenangkan bagi kita semua. Untuk menjaga kenyamanan lingkungan kita bersama, kami ingin mengingatkan beberapa hal penting: Kebersihan: Mohon pastikan sampah rumah tangga sudah diletakkan di tempat yang seharusnya sebelum jadwal pengangkutan sampah. Keamanan: Bagi Bapak/Ibu yang akan bepergian meninggalkan rumah dalam waktu yang cukup lama, mohon informasikan kepada pengurus RT atau tetangga terdekat. Kegiatan: Jika ada agenda atau kegiatan warga yang ingin disosialisasikan, silakan hubungi pengurus RT melalui portal ini atau melalui grup warga. Terima kasih atas perhatian dan kerja sama Bapak/Ibu dalam menjaga kerukunan serta kebersihan lingkungan kita. Salam hangat. Pengurus RT 09 / RW 14',
        kategori='Info Warga',
        prioritas='Biasa',
        tanggal=date(2026, 4, 10),
        is_aktif=True,
        author='Pengurus RT 09 / RW 14'
    )
    db.session.add_all([p1, p2])

    # 8. Seed Inventaris
    inv1 = Inventaris(
        kode_barang='INV-RT09-001',
        nama_barang='Sound System Portable Wireless (Speaker + Mic)',
        kategori='Elektronik / Audio',
        jumlah=2,
        satuan='Unit',
        kondisi='Baik',
        lokasi='Gudang RT 09',
        tgl_pengadaan=date(2025, 8, 10),
        nilai_perolehan=2500000.0,
        status='Tersedia',
        catatan='Digunakan untuk rapat warga, pengajian, dan senam'
    )
    inv2 = Inventaris(
        kode_barang='INV-RT09-002',
        nama_barang='Tenda Lipat 3x3 Meter',
        kategori='Tenda & Kursi',
        jumlah=4,
        satuan='Unit',
        kondisi='Baik',
        lokasi='Gudang RT 09',
        tgl_pengadaan=date(2025, 6, 1),
        nilai_perolehan=3200000.0,
        status='Dipinjam',
        catatan='Warna biru Paguyuban RT'
    )
    inv3 = Inventaris(
        kode_barang='INV-RT09-003',
        nama_barang='Kursi Plastik Napolly',
        kategori='Tenda & Kursi',
        jumlah=50,
        satuan='Buah',
        kondisi='Baik',
        lokasi='Gudang RT 09',
        tgl_pengadaan=date(2024, 11, 20),
        nilai_perolehan=3500000.0,
        status='Tersedia',
        catatan='Stempel cat RT 09 di sandaran'
    )
    inv4 = Inventaris(
        kode_barang='INV-RT09-004',
        nama_barang='Mesin Potong Rumput Gendong',
        kategori='Alat Kebersihan',
        jumlah=1,
        satuan='Unit',
        kondisi='Rusak Berat',
        lokasi='Pos Satpam',
        tgl_pengadaan=date(2023, 3, 15),
        nilai_perolehan=1800000.0,
        status='Disposal',
        catatan='Piston macet dan blok mesin pecah setelah 3 tahun pemakaian'
    )
    db.session.add_all([inv1, inv2, inv3, inv4])
    db.session.flush()

    pinjam1 = PeminjamanInventaris(
        inventaris_id=inv2.id,
        warga_id=warga_demo.id,
        nama_peminjam='Budi Santoso',
        no_hp='085712345678',
        jumlah_pinjam=2,
        tgl_pinjam=date(2026, 4, 18),
        tgl_kembali_rencana=date(2026, 4, 20),
        keperluan='Acara syukuran khitanan di rumah',
        status='Dipinjam',
        catatan='Telah diambil oleh peminjam'
    )
    disp1 = DisposalInventaris(
        inventaris_id=inv4.id,
        tgl_disposal=date(2026, 3, 10),
        alasan='Kerusakan total pada mesin penggerak, biaya servis melebihi harga unit baru',
        metode='Dibuang / Rusak Total',
        nilai_residu=150000.0,
        disetujui_oleh='H. Bambang Sutrisno (Ketua RT 09)',
        catatan='Hasil penjualan besi tua Rp 150.000 disetorkan ke Kas RT'
    )
    db.session.add_all([pinjam1, disp1])

    # 9. Seed Persuratan
    s1 = Surat(
        nomor_surat='001/RT-09/RW-14/IV/2026',
        warga_id=warga_demo.id,
        jenis_surat='Surat Pengantar RT (KTP/KK)',
        keperluan='Pengurusan perpanjangan dan pembaruan Kartu Keluarga di Kelurahan',
        data_tambahan=json.dumps({'keterangan': 'Pembaruan data anggota keluarga baru'}),
        status='Disetujui',
        tanggal_pengajuan=datetime(2026, 4, 12, 9, 30),
        tanggal_disetujui=datetime(2026, 4, 12, 14, 0),
        approved_by='H. Bambang Sutrisno',
        catatan_petugas='Dokumen pendukung lengkap dan valid'
    )
    s2 = Surat(
        nomor_surat='002/RT-09/RW-14/IV/2026',
        warga_id=warga_ahmad.id,
        jenis_surat='Surat Keterangan Domisili',
        keperluan='Keterangan domisili tinggal warga kontrak di Blok G No. 65',
        data_tambahan=json.dumps({'lama_tinggal': '2 bulan'}),
        status='Disetujui',
        tanggal_pengajuan=datetime(2026, 4, 14, 11, 15),
        tanggal_disetujui=datetime(2026, 4, 14, 15, 20),
        approved_by='H. Bambang Sutrisno',
        catatan_petugas='Warga pengontrak terdaftar di RT 09'
    )
    db.session.add_all([s1, s2])

    # 10. Seed Pelaporan
    lap1 = Laporan(
        warga_id=warga_demo.id,
        nama_pelapor='Budi Santoso',
        judul='Lampu Penerangan Jalan Umum (PJU) Blok B Depan No. 12 Mati',
        kategori='Infrastruktur',
        deskripsi='Lampu tiang PJU di depan rumah B3/12 mati total sejak kemarin malam, kondisi jalan menjadi gelap dan rawan keamanan.',
        lokasi='Jl. De Naila Village Blok G Blok B depan Rumah No. 12',
        foto='lampu_mati_demo.jpg',
        status='Diproses',
        tindak_lanjut='Pengurus sudah berkoordinasi dengan petugas PLN dan seksi keamanan untuk penggantian bohlam LED 50W',
        tanggapan_petugas='Jadwal penggantian bohlam sore ini pukul 17:00 WIB oleh tim teknis RT.',
        created_at=datetime(2026, 4, 16, 20, 15),
        updated_at=datetime(2026, 4, 17, 8, 30)
    )
    lap2 = Laporan(
        warga_id=warga_ahmad.id,
        nama_pelapor='Ahmad Budiman Sujatmiko',
        judul='Permohonan Saluran Air Tambahan di Depan Gang Blok G',
        kategori='Infrastruktur',
        deskripsi='Saat hujan deras terdapat sedikit genangan air di depan Blok G No. 65.',
        lokasi='Depan Rumah Blok G No. 65',
        status='Menunggu',
        tanggapan_petugas='Laporan diterima, akan dicek oleh seksi kebersihan dan infrastruktur.',
        created_at=datetime(2026, 4, 17, 10, 0)
    )
    db.session.add_all([lap1, lap2])

    db.session.commit()
    print("Database seeding with Rumah, Keterhunian & Smart Login completed successfully!")
    print(f"Total Warga: {Warga.query.count()}")
    print(f"Total Unit Rumah: {Rumah.query.count()}")
    print(f"Iuran Lunas: {Iuran.query.filter_by(status='Lunas').count()}")
    print(f"Belum Lunas: {Iuran.query.filter_by(status='Belum Lunas').count()}")
    print(f"Menunggu Konfirmasi: {Iuran.query.filter_by(status='Menunggu Konfirmasi').count()}")
    pemasukan = db.session.query(db.func.sum(TransaksiKas.jumlah)).filter_by(jenis='Pemasukan').scalar() or 0
    pengeluaran = db.session.query(db.func.sum(TransaksiKas.jumlah)).filter_by(jenis='Pengeluaran').scalar() or 0
    print(f"Total Pemasukan: Rp {pemasukan:,.0f} | Pengeluaran: Rp {pengeluaran:,.0f} | Kas: Rp {pemasukan - pengeluaran:,.0f}")

if __name__ == '__main__':
    from flask import Flask
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///portalrt.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    with app.app_context():
        seed_database()
