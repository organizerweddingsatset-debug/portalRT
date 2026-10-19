from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class BaseModel(db.Model):
    __abstract__ = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

class User(BaseModel):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    nama = db.Column(db.String(120), nullable=False)
    
    # Peran (Role): 'superadmin', 'ketua_rt', 'pengurus', 'warga' (alias legacy: 'pejabat')
    role = db.Column(db.String(30), default='warga', nullable=False)
    
    # Optional raw storage fallback for user_type in database
    _user_type = db.Column('user_type', db.String(30), nullable=True)
    
    # Warga ID: NULL untuk Superadmin (Superadmin bukan warga!)
    warga_id = db.Column(db.Integer, db.ForeignKey('warga.id', ondelete='SET NULL'), nullable=True)
    no_hp = db.Column(db.String(30), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    warga = db.relationship('Warga', backref=db.backref('user_account', uselist=False))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def user_type(self):
        """
        Dihitung dinamis dari relasi kepemilikan aset unit rumah di RT 09 (Single Source of Truth):
        - Superadmin: Bukan Warga (warga_id = None)
        - Warga Pemilik: Memiliki rumah di RT 09 atau berstatus tinggal Tetap
        - Warga Kontrak: Mengontrak unit rumah di RT 09 atau berstatus tinggal Kontrak
        """
        if not self.warga_id or self.role == 'superadmin':
            return 'superadmin'
        if not self.warga:
            return 'superadmin'

        # Cek kepemilikan unit rumah di RT 09
        if hasattr(self.warga, 'rumah_dimiliki') and self.warga.rumah_dimiliki.count() > 0:
            return 'warga_pemilik'

        # Cek apakah menghuni unit rumah yang statusnya Dikontrakkan
        if hasattr(self.warga, 'rumah_dihuni'):
            rumah_kontrak = self.warga.rumah_dihuni.filter_by(status_huni='Dikontrakkan').first()
            if rumah_kontrak:
                return 'warga_kontrak'

        if self.warga.status_tinggal in ['Kontrak', 'Kost']:
            return 'warga_kontrak'

        if self._user_type:
            return self._user_type

        return 'warga_pemilik'

    @user_type.setter
    def user_type(self, val):
        self._user_type = val

    @property
    def role_display(self):
        mapping = {
            'superadmin': 'Superadmin',
            'ketua_rt': 'Ketua RT',
            'pejabat': 'Ketua RT',
            'pengurus': 'Pengurus',
            'warga': 'Warga',
        }
        return mapping.get(self.role, self.role.replace('_', ' ').title())

    @property
    def user_type_display(self):
        mapping = {
            'superadmin': 'Superadmin',
            'warga_pemilik': 'Warga Pemilik',
            'warga_kontrak': 'Warga Kontrak',
        }
        return mapping.get(self.user_type, self.user_type.replace('_', ' ').title())

    def is_superadmin(self):
        return self.role == 'superadmin' or self.user_type == 'superadmin'

    def is_ketua_rt(self):
        return self.role in ['ketua_rt', 'pejabat']

    def is_pejabat(self):
        return self.is_ketua_rt()

    def is_pengurus(self):
        return self.role in ['superadmin', 'ketua_rt', 'pejabat', 'pengurus']

    def is_admin(self):
        return self.role in ['superadmin', 'ketua_rt', 'pejabat', 'pengurus']

    def is_warga_biasa(self):
        return self.role == 'warga'

    def is_warga(self):
        """Apakah pengguna terdaftar sebagai warga RT?
        Aturan RT: Superadmin BUKAN warga (warga_id == None)!"""
        return self.user_type in ['warga_pemilik', 'warga_kontrak'] and self.warga_id is not None

    def is_warga_pemilik(self):
        return self.user_type == 'warga_pemilik'

    def is_warga_kontrak(self):
        return self.user_type == 'warga_kontrak'


class Warga(BaseModel):
    __tablename__ = 'warga'
    
    id = db.Column(db.Integer, primary_key=True)
    nik = db.Column(db.String(20), unique=True, nullable=False, index=True)
    no_kk = db.Column(db.String(20), nullable=False, index=True)
    nama = db.Column(db.String(120), nullable=False)
    jenis_kelamin = db.Column(db.String(20), nullable=False) # 'Laki-laki', 'Perempuan'
    tempat_lahir = db.Column(db.String(60), nullable=True)
    tanggal_lahir = db.Column(db.Date, nullable=True)
    agama = db.Column(db.String(30), default='Islam')
    pekerjaan = db.Column(db.String(80), nullable=True)
    status_perkawinan = db.Column(db.String(30), default='Kawin') # 'Kawin', 'Belum Kawin', 'Cerai Hidup', 'Cerai Mati'
    status_keluarga = db.Column(db.String(30), default='Kepala Keluarga') # 'Kepala Keluarga', 'Istri', 'Anak', 'Famili Lain'
    status_tinggal = db.Column(db.String(30), default='Tetap') # 'Tetap', 'Kontrak', 'Kost'
    no_rumah = db.Column(db.String(20), nullable=True)
    alamat = db.Column(db.Text, nullable=True)
    rt_rw = db.Column(db.String(20), default='09/14')
    no_hp = db.Column(db.String(30), nullable=True)
    email = db.Column(db.String(100), nullable=True)
    is_aktif = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    iuran_list = db.relationship('Iuran', backref='warga', lazy='dynamic', cascade='all, delete-orphan')
    surat_list = db.relationship('Surat', backref='warga', lazy='dynamic')
    laporan_list = db.relationship('Laporan', backref='warga', lazy='dynamic')
    peminjaman_list = db.relationship('PeminjamanInventaris', backref='warga', lazy='dynamic')


class Rumah(BaseModel):
    __tablename__ = 'rumah'
    
    id = db.Column(db.Integer, primary_key=True)
    no_rumah = db.Column(db.String(30), unique=True, nullable=False, index=True) # e.g. 'G/65', 'A2/05', 'B3/12'
    blok = db.Column(db.String(10), nullable=True) # e.g. 'G', 'A2', 'B3'
    nomor = db.Column(db.String(10), nullable=True) # e.g. '65', '05', '12'
    alamat = db.Column(db.Text, nullable=True)
    
    # Pemilik Rumah (Warga Tetap / Pemilik Sertifikat)
    pemilik_id = db.Column(db.Integer, db.ForeignKey('warga.id', ondelete='SET NULL'), nullable=True)
    
    # Penghuni Aktif (Penanggung Jawab Iuran Aktif: Pemilik atau Pengontrak)
    penghuni_aktif_id = db.Column(db.Integer, db.ForeignKey('warga.id', ondelete='SET NULL'), nullable=True)
    
    # Status Huni: 'Dihuni Pemilik', 'Dikontrakkan', 'Kosong'
    status_huni = db.Column(db.String(30), default='Dihuni Pemilik')
    tipe_penghuni = db.Column(db.String(30), default='Pemilik') # 'Pemilik', 'Pengontrak'
    tgl_mulai_sewa = db.Column(db.Date, nullable=True)
    tgl_selesai_sewa = db.Column(db.Date, nullable=True)
    catatan = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def blok_nomor(self):
        return self.no_rumah or f"{self.blok}/{self.nomor}"

    # Relationships
    pemilik = db.relationship('Warga', foreign_keys=[pemilik_id], backref=db.backref('rumah_dimiliki', lazy='dynamic'))
    penghuni_aktif = db.relationship('Warga', foreign_keys=[penghuni_aktif_id], backref=db.backref('rumah_dihuni', lazy='dynamic'))
    riwayat_keterhunian = db.relationship('RiwayatKeterhunian', backref='rumah', lazy='dynamic', cascade='all, delete-orphan')
    iuran_list = db.relationship('Iuran', backref='rumah', lazy='dynamic')


class RiwayatKeterhunian(BaseModel):
    __tablename__ = 'riwayat_keterhunian'

    id = db.Column(db.Integer, primary_key=True)
    rumah_id = db.Column(db.Integer, db.ForeignKey('rumah.id', ondelete='CASCADE'), nullable=False)
    warga_id = db.Column(db.Integer, db.ForeignKey('warga.id', ondelete='SET NULL'), nullable=True)
    tipe_penghuni = db.Column(db.String(30), default='Pengontrak') # 'Pengontrak', 'Pemilik'
    tgl_mulai = db.Column(db.Date, nullable=True)
    tgl_selesai = db.Column(db.Date, nullable=True) # None jika masih aktif
    is_aktif = db.Column(db.Boolean, default=True)
    status_tunggakan = db.Column(db.String(30), default='Lunas') # 'Lunas', 'Ada Tunggakan'
    catatan_serah_terima = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    warga = db.relationship('Warga')


class Iuran(BaseModel):
    __tablename__ = 'iuran'
    
    id = db.Column(db.Integer, primary_key=True)
    # Tautan ke Objek Rumah (agar riwayat rumah utuh abadi lintas pergantian penyewa)
    rumah_id = db.Column(db.Integer, db.ForeignKey('rumah.id', ondelete='SET NULL'), nullable=True)
    
    # Snapshot Pembayar pada periode tersebut
    warga_id = db.Column(db.Integer, db.ForeignKey('warga.id', ondelete='CASCADE'), nullable=False)
    tipe_pembayar = db.Column(db.String(30), default='Penghuni Aktif') # 'Pengontrak', 'Pemilik'
    
    periode_bulan = db.Column(db.Integer, nullable=False) # 1 - 12
    periode_tahun = db.Column(db.Integer, nullable=False) # 2026
    jumlah = db.Column(db.Float, default=15000.0, nullable=False)
    status = db.Column(db.String(30), default='Belum Lunas') # 'Lunas', 'Belum Lunas', 'Menunggu Konfirmasi'
    metode_bayar = db.Column(db.String(50), default='Tunai / Cash') # 'Tunai / Cash', 'Transfer Bank', 'QRIS'
    tanggal_bayar = db.Column(db.DateTime, nullable=True)
    bukti_transfer = db.Column(db.String(255), nullable=True)
    catatan = db.Column(db.Text, nullable=True)
    verified_by = db.Column(db.String(100), nullable=True)
    verified_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Integrasi Payment Gateway Mayar.id
    mayar_invoice_id = db.Column(db.String(100), nullable=True, index=True)
    mayar_transaction_id = db.Column(db.String(100), nullable=True, index=True)
    mayar_payment_url = db.Column(db.String(255), nullable=True)

    __table_args__ = (
        db.UniqueConstraint('warga_id', 'periode_bulan', 'periode_tahun', name='uq_warga_periode'),
    )


class TransaksiKas(BaseModel):
    __tablename__ = 'transaksi_kas'
    
    id = db.Column(db.Integer, primary_key=True)
    kode_transaksi = db.Column(db.String(50), unique=True, nullable=False)
    jenis = db.Column(db.String(20), nullable=False) # 'Pemasukan', 'Pengeluaran'
    kategori = db.Column(db.String(60), nullable=False) 
    # Kategori Pemasukan: 'Iuran Warga', 'Donasi / Sumbangan', 'Kas Awal', 'Penyewaan Inventaris', 'Lain-lain'
    # Kategori Pengeluaran: 'Operasional RT', 'Kegiatan Warga', 'Kebersihan Lingkungan', 'Keamanan', 'Pemeliharaan Fasilitas', 'Sosial & Santunan', 'Lain-lain'
    judul = db.Column(db.String(150), nullable=False)
    jumlah = db.Column(db.Float, nullable=False)
    tanggal = db.Column(db.Date, nullable=False, default=date.today)
    keterangan = db.Column(db.Text, nullable=True)
    bukti_transaksi = db.Column(db.String(255), nullable=True)
    iuran_id = db.Column(db.Integer, db.ForeignKey('iuran.id', ondelete='SET NULL'), nullable=True)
    created_by = db.Column(db.String(100), default='Admin RT')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Surat(BaseModel):
    __tablename__ = 'surat'
    
    id = db.Column(db.Integer, primary_key=True)
    nomor_surat = db.Column(db.String(100), unique=True, nullable=False)
    warga_id = db.Column(db.Integer, db.ForeignKey('warga.id', ondelete='CASCADE'), nullable=False)
    jenis_surat = db.Column(db.String(100), nullable=False) 
    # 'Surat Pengantar RT (KTP/KK)', 'Surat Keterangan Domisili', 'Surat Keterangan Usaha (SKU)',
    # 'Surat Keterangan Tidak Mampu (SKTM)', 'Surat Keterangan Kematian', 'Surat Keterangan Kelahiran', 'Surat Izin Keramaian'
    keperluan = db.Column(db.Text, nullable=False)
    data_tambahan = db.Column(db.Text, nullable=True) # JSON format string for template-specific fields
    status = db.Column(db.String(30), default='Diajukan') # 'Diajukan', 'Diproses', 'Disetujui', 'Ditolak'
    tanggal_pengajuan = db.Column(db.DateTime, default=datetime.utcnow)
    tanggal_disetujui = db.Column(db.DateTime, nullable=True)
    catatan_petugas = db.Column(db.Text, nullable=True)
    approved_by = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Pengumuman(BaseModel):
    __tablename__ = 'pengumuman'
    
    id = db.Column(db.Integer, primary_key=True)
    judul = db.Column(db.String(200), nullable=False)
    konten = db.Column(db.Text, nullable=False)
    kategori = db.Column(db.String(50), default='Info Warga') # 'Penting', 'Info Warga', 'Kegiatan', 'Iuran', 'Keamanan'
    prioritas = db.Column(db.String(20), default='Biasa') # 'Tinggi', 'Biasa'
    tanggal = db.Column(db.Date, default=date.today)
    is_aktif = db.Column(db.Boolean, default=True)
    lampiran = db.Column(db.String(255), nullable=True)
    author = db.Column(db.String(100), default='Pengurus RT 09 / RW 14')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Inventaris(BaseModel):
    __tablename__ = 'inventaris'
    
    id = db.Column(db.Integer, primary_key=True)
    kode_barang = db.Column(db.String(50), unique=True, nullable=False)
    nama_barang = db.Column(db.String(150), nullable=False)
    kategori = db.Column(db.String(60), default='Peralatan') # 'Elektronik / Audio', 'Tenda & Kursi', 'Alat Kebersihan', 'Peralatan Masak', 'Keamanan / Pos Ronda', 'Lain-lain'
    jumlah = db.Column(db.Integer, default=1, nullable=False)
    satuan = db.Column(db.String(30), default='Unit')
    kondisi = db.Column(db.String(30), default='Baik') # 'Baik', 'Rusak Ringan', 'Rusak Berat'
    lokasi = db.Column(db.String(100), default='Gudang RT 09')
    tgl_pengadaan = db.Column(db.Date, nullable=True)
    nilai_perolehan = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(30), default='Tersedia') # 'Tersedia', 'Dipinjam', 'Disposal'
    catatan = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    peminjaman = db.relationship('PeminjamanInventaris', backref='barang', lazy='dynamic')
    disposal = db.relationship('DisposalInventaris', backref='barang', uselist=False)


class PeminjamanInventaris(BaseModel):
    __tablename__ = 'peminjaman_inventaris'
    
    id = db.Column(db.Integer, primary_key=True)
    inventaris_id = db.Column(db.Integer, db.ForeignKey('inventaris.id', ondelete='CASCADE'), nullable=False)
    warga_id = db.Column(db.Integer, db.ForeignKey('warga.id', ondelete='SET NULL'), nullable=True)
    nama_peminjam = db.Column(db.String(100), nullable=False)
    no_hp = db.Column(db.String(30), nullable=True)
    jumlah_pinjam = db.Column(db.Integer, default=1, nullable=False)
    tgl_pinjam = db.Column(db.Date, nullable=False)
    tgl_kembali_rencana = db.Column(db.Date, nullable=False)
    tgl_kembali_aktual = db.Column(db.Date, nullable=True)
    keperluan = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(30), default='Menunggu') # 'Menunggu', 'Disetujui', 'Ditolak', 'Dipinjam', 'Selesai'
    catatan = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class DisposalInventaris(BaseModel):
    __tablename__ = 'disposal_inventaris'
    
    id = db.Column(db.Integer, primary_key=True)
    inventaris_id = db.Column(db.Integer, db.ForeignKey('inventaris.id', ondelete='CASCADE'), unique=True, nullable=False)
    tgl_disposal = db.Column(db.Date, nullable=False, default=date.today)
    alasan = db.Column(db.String(255), nullable=False)
    metode = db.Column(db.String(60), default='Dibuang / Rusak Total') # 'Dibuang / Rusak Total', 'Dilelang / Dijual', 'Dihibahkan'
    nilai_residu = db.Column(db.Float, default=0.0)
    disetujui_oleh = db.Column(db.String(100), default='Ketua RT 09')
    catatan = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Laporan(BaseModel):
    __tablename__ = 'laporan'
    
    id = db.Column(db.Integer, primary_key=True)
    warga_id = db.Column(db.Integer, db.ForeignKey('warga.id', ondelete='SET NULL'), nullable=True)
    nama_pelapor = db.Column(db.String(100), nullable=False)
    judul = db.Column(db.String(150), nullable=False)
    kategori = db.Column(db.String(50), default='Lingkungan') # 'Lingkungan', 'Keamanan', 'Infrastruktur', 'Kebersihan', 'Sosial', 'Kebutuhan Warga', 'Lainnya'
    deskripsi = db.Column(db.Text, nullable=False)
    lokasi = db.Column(db.String(150), nullable=True)
    foto = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(30), default='Menunggu') # 'Menunggu', 'Diproses', 'Selesai', 'Ditolak'
    tindak_lanjut = db.Column(db.Text, nullable=True)
    tanggapan_petugas = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Pengaturan(BaseModel):
    __tablename__ = 'pengaturan'
    
    id = db.Column(db.Integer, primary_key=True)
    kunci = db.Column(db.String(80), unique=True, nullable=False, index=True)
    nilai = db.Column(db.Text, nullable=True)
    kategori = db.Column(db.String(50), default='umum') # 'identitas', 'notifikasi', 'qris', 'import', 'umum'
    deskripsi = db.Column(db.String(255), nullable=True)

    def __init__(self, kunci=None, nilai=None, kategori='umum', deskripsi=None, **kwargs):
        super().__init__(**kwargs)
        self.kunci = kunci
        self.nilai = nilai
        self.kategori = kategori
        self.deskripsi = deskripsi

    @classmethod
    def get(cls, key, default=None):
        setting = cls.query.filter_by(kunci=key).first()
        return setting.nilai if setting and setting.nilai is not None else default

    @classmethod
    def set(cls, key, value, kategori='umum', deskripsi=None):
        setting = cls.query.filter_by(kunci=key).first()
        if not setting:
            setting = cls(kunci=key, nilai=str(value), kategori=kategori, deskripsi=deskripsi)
            db.session.add(setting)
        else:
            setting.nilai = str(value)
            if deskripsi:
                setting.deskripsi = deskripsi
        db.session.commit()
