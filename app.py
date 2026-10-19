import os
import io
import csv
import json
from datetime import datetime, date
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for, 
    flash, session, send_file, Response, abort, jsonify
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

import re
import urllib.request
import urllib.error
import urllib.parse
from models import (
    db, User, Warga, Rumah, RiwayatKeterhunian, Iuran, TransaksiKas, Surat, 
    Pengumuman, Inventaris, PeminjamanInventaris, DisposalInventaris, 
    Laporan, Pengaturan
)
from seed_data import seed_database

app = Flask(__name__)
app.config['SECRET_KEY'] = 'portal-rt09-secret-key-2026-secure'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///portalrt.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # 16 MB

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db.init_app(app)

def check_and_upgrade_db():
    """Memastikan kolom tambahan seperti Mayar ID dan verified_at ada pada database SQLite eksisting."""
    with app.app_context():
        try:
            from sqlalchemy import text
            with db.engine.connect() as conn:
                res = conn.execute(text("PRAGMA table_info(iuran)"))
                cols = [r[1] for r in res.fetchall()]
                if 'mayar_invoice_id' not in cols:
                    conn.execute(text("ALTER TABLE iuran ADD COLUMN mayar_invoice_id VARCHAR(100)"))
                if 'mayar_transaction_id' not in cols:
                    conn.execute(text("ALTER TABLE iuran ADD COLUMN mayar_transaction_id VARCHAR(100)"))
                if 'mayar_payment_url' not in cols:
                    conn.execute(text("ALTER TABLE iuran ADD COLUMN mayar_payment_url VARCHAR(255)"))
                if 'verified_at' not in cols:
                    conn.execute(text("ALTER TABLE iuran ADD COLUMN verified_at DATETIME"))
                if 'kode_pembayaran' not in cols:
                    conn.execute(text("ALTER TABLE iuran ADD COLUMN kode_pembayaran VARCHAR(50)"))
                conn.commit()
            
            # Upgrade template notifikasi tagihan ke format rincian jatuh tempo tgl 15 + tunggakan
            try:
                curr_tpl = Pengaturan.get('template_tagihan')
                if curr_tpl and ('Halo Bapak/Ibu {nama}, kami menginformasikan tagihan' in curr_tpl or 'Batas Jatuh Tempo: *Tanggal 15' not in curr_tpl):
                    new_tpl = (
                        "*PEMBERITAHUAN & PENGINGAT IURAN WARGA RT 09 / RW 14*\n"
                        "_Perumahan De Naila Village_\n\n"
                        "Yth. Bapak/Ibu *{nama}*\n"
                        "Penghuni Rumah: *{no_rumah}*\n\n"
                        "Semoga Bapak/Ibu dan keluarga senantiasa dalam keadaan sehat walafiat.\n\n"
                        "Melalui pesan ini, kami menyampaikan rincian kewajiban iuran kas Paguyuban RT 09:\n\n"
                        "════════════════════════════════════\n"
                        "📅 *1. NOMINAL BULAN INI (JATUH TEMPO TGL 15)*\n"
                        "• Periode: *Bulan {bulan_ini} / {tahun_ini} ({nama_bulan_ini})*\n"
                        "• Batas Jatuh Tempo: *Tanggal 15 {nama_bulan_ini} {tahun_ini}*\n"
                        "• Nominal: *Rp {nominal_bulan_ini}*\n"
                        "• Status: *{status_bulan_ini}*\n\n"
                        "⚠️ *2. NOMINAL TUNGGAKAN BULAN SEBELUMNYA*\n"
                        "{rincian_tunggakan}\n"
                        "• Subtotal Tunggakan: *Rp {subtotal_tunggakan}*\n\n"
                        "════════════════════════════════════\n"
                        "💵 *TOTAL PEMBAYARAN:*\n"
                        "*(Bulan Ini + Tunggakan Belum Lunas)*\n"
                        "👉 *Rp {total_keseluruhan}*\n"
                        "════════════════════════════════════\n\n"
                        "💳 *Metode Pembayaran Resmi RT 09:*\n"
                        "1. *Portal Warga RT 09 (QRIS Instan Dinamis & Bayar Sekaligus):*\n"
                        "   https://portalrt.id/iuran\n"
                        "2. *Transfer Bank Rekening Kas RT:*\n"
                        "   Bank Central Asia (BCA) No. Rek: *8830-1928-31*\n"
                        "   Atas Nama: *PAGUYUBAN WARGA RT 09*\n"
                        "3. *Tunai / Cash:*\n"
                        "   Langsung ke Bendahara RT (Bpk. Ahmad Fauzi / Rumah A2/05)\n\n"
                        "_Setelah pembayaran terverifikasi, Kuitansi Resmi Digital Sah otomatis dapat diunduh melalui portal warga._\n\n"
                        "Mohon konfirmasi jika telah melakukan pembayaran atau unggah bukti transfer di portal. Terima kasih atas kerja sama dan partisipasi Bapak/Ibu demi kenyamanan lingkungan kita bersama. 🙏\n\n"
                        "Salam hormat,\n"
                        "*Pengurus Paguyuban RT 09 / RW 14*"
                    )
                    Pengaturan.set('template_tagihan', new_tpl, kategori='notifikasi', deskripsi='Template Pesan Tagihan & Pengingat Iuran (Bulan Ini tgl 15 + Tunggakan)')
            except Exception:
                pass
        except Exception:
            pass

check_and_upgrade_db()

# -------------------------------------------------------------
# AUTH & CONTEXT HELPERS
# -------------------------------------------------------------
def get_current_user():
    user_id = session.get('user_id')
    if user_id:
        return db.session.get(User, user_id)
    return None

def resolve_user_for_login(login_input):
    """
    Menemukan akun User berdasarkan:
    1. Username langsung (e.g. 'admin', 'pengurus', 'pejabat', 'warga1', 'AhmadG65')
    2. Smart Login Warga: Kombinasi Nama + Blok & No. Rumah
       Contoh: 'Ahmad budiman Sujatmiko' di Blok G No. 65
       -> AhmadG65, BudimanG65, SujatmikoG65, ahmadg65, budimang65, Ahmad G65, Ahmad G/65, dll.
    """
    if not login_input:
        return None

    raw_input = login_input.strip()
    clean_input = re.sub(r'[^a-zA-Z0-9]', '', raw_input).lower()
    if not clean_input:
        return None

    # 1. Cek direct match username di DB
    user = User.query.filter(db.func.lower(User.username) == raw_input.lower()).first()
    if user:
        return user

    user = User.query.filter(db.func.lower(User.username) == clean_input).first()
    if user:
        return user

    # 1b. Alias match untuk Superadmin dan Ketua RT
    if clean_input == 'superadmin':
        admin_u = User.query.filter_by(role='superadmin').first()
        if admin_u:
            return admin_u
    if clean_input in ['pejabat', 'ketuart', 'pakrt']:
        ketua_u = User.query.filter(User.role.in_(['ketua_rt', 'pejabat'])).first()
        if ketua_u:
            return ketua_u

    # 2. Smart Login Warga Matcher (Nama + Blok No. Rumah)
    all_warga = Warga.query.filter_by(is_aktif=True).all()
    for w in all_warga:
        # Pecah kata nama warga (abaikan token 1 huruf seperti 'H.')
        name_parts = [re.sub(r'[^a-zA-Z0-9]', '', p).lower() for p in w.nama.split() if len(p) >= 2]
        
        # Kumpulkan varian representasi nomor rumah/blok
        house_variants = set()
        if w.no_rumah:
            clean_nr = re.sub(r'[^a-zA-Z0-9]', '', w.no_rumah).lower()
            if clean_nr:
                house_variants.add(clean_nr) # e.g. 'g65', 'b312', 'a101'
            parts = re.split(r'[/ \-_]', w.no_rumah)
            if len(parts) >= 2:
                b = re.sub(r'[^a-zA-Z0-9]', '', parts[0]).lower()
                n = re.sub(r'[^a-zA-Z0-9]', '', parts[1]).lower()
                if b and n:
                    house_variants.add(f"{b}{n}")
                    house_variants.add(n)
                    n_stripped = n.lstrip('0')
                    if n_stripped:
                        house_variants.add(f"{b}{n_stripped}")
                        house_variants.add(n_stripped)

        # Cek objek rumah jika terkait
        r_obj = (w.rumah_dihuni.first() if hasattr(w, 'rumah_dihuni') and w.rumah_dihuni else None) or \
                (w.rumah_dimiliki.first() if hasattr(w, 'rumah_dimiliki') and w.rumah_dimiliki else None)
        if r_obj:
            b = re.sub(r'[^a-zA-Z0-9]', '', r_obj.blok or '').lower()
            n = re.sub(r'[^a-zA-Z0-9]', '', r_obj.nomor or '').lower()
            if b and n:
                house_variants.add(f"{b}{n}")
                house_variants.add(n)
                n_str = n.lstrip('0')
                if n_str:
                    house_variants.add(f"{b}{n_str}")
                    house_variants.add(n_str)
            if r_obj.no_rumah:
                clean_r_nr = re.sub(r'[^a-zA-Z0-9]', '', r_obj.no_rumah).lower()
                if clean_r_nr:
                    house_variants.add(clean_r_nr)

        # Cocokkan kombinasi: setiap bagian nama + setiap variasi nomor rumah
        for name_tok in name_parts:
            for h_var in house_variants:
                if clean_input in (f"{name_tok}{h_var}", f"{h_var}{name_tok}"):
                    # Temukan User account milik warga ini
                    matched_user = User.query.filter_by(warga_id=w.id).first()
                    if matched_user:
                        return matched_user
                    
                    # Jika belum ada user account, buatkan otomatis
                    new_uname = f"{name_tok.title()}{h_var.upper()}"
                    chk = User.query.filter_by(username=new_uname).first()
                    if chk:
                        new_uname = f"{new_uname}_{w.id}"
                    
                    u_type = 'warga_kontrak' if (w.status_tinggal == 'Kontrak' or (r_obj and r_obj.tipe_penghuni == 'Pengontrak')) else 'warga_pemilik'
                    new_user = User(
                        username=new_uname,
                        nama=w.nama,
                        role='warga',
                        user_type=u_type,
                        warga_id=w.id,
                        no_hp=w.no_hp,
                        is_active=True
                    )
                    new_user.set_password('warga123')
                    db.session.add(new_user)
                    db.session.commit()
                    return new_user

    return None

def terbilang_rupiah(n):
    """Mengubah nominal angka menjadi format terbilang resmi bahasa Indonesia"""
    try:
        n = int(n)
    except (ValueError, TypeError):
        return "Nol Rupiah"

    if n == 0:
        return "Nol Rupiah"

    satuan = ["", "Satu", "Dua", "Tiga", "Empat", "Lima", "Enam", "Tujuh", "Delapan", "Sembilan", "Sepuluh", "Sebelas"]

    def _bilang(num):
        if num < 0:
            return "Minus " + _bilang(abs(num))
        if num < 12:
            return satuan[num]
        elif num < 20:
            return _bilang(num - 10) + " Belas"
        elif num < 100:
            return _bilang(num // 10) + " Puluh " + _bilang(num % 10)
        elif num < 200:
            return "Seratus " + _bilang(num - 100)
        elif num < 1000:
            return _bilang(num // 100) + " Ratus " + _bilang(num % 100)
        elif num < 2000:
            return "Seribu " + _bilang(num - 1000)
        elif num < 1000000:
            return _bilang(num // 1000) + " Ribu " + _bilang(num % 1000)
        elif num < 1000000000:
            return _bilang(num // 1000000) + " Juta " + _bilang(num % 1000000)
        else:
            return _bilang(num // 1000000000) + " Miliar " + _bilang(num % 1000000000)

    hasil = _bilang(n)
    clean = " ".join(hasil.split())
    return f"{clean} Rupiah" if clean else "Nol Rupiah"

@app.context_processor
def inject_global_data():
    current_user = get_current_user()
    nama_rt = Pengaturan.get('nama_rt', 'RT 09')
    nama_rw = Pengaturan.get('nama_rw', 'RW 14')
    return {
        'current_user': current_user,
        'global_rt': f"{nama_rt} / {nama_rw}",
        'now_year': 2026,
        'terbilang_rupiah': terbilang_rupiah,
        'get_setting': Pengaturan.get,
        'qris_payload': Pengaturan.get('qris_payload', '')
    }

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Silakan masuk terlebih dahulu untuk mengakses portal.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user or not user.is_admin():
            flash('Akses ditolak. Fitur ini hanya untuk Pengurus, Ketua RT, atau Superadmin.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def superadmin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user or not user.is_superadmin():
            flash('Akses ditolak. Fitur ini khusus untuk Superadmin sistem.', 'danger')
            if user and user.is_admin():
                return redirect(url_for('pengaturan_index'))
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def ketua_rt_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user or not (user.is_ketua_rt() or user.is_superadmin()):
            flash('Akses ditolak. Fitur ini memerlukan wewenang Ketua RT.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function


# -------------------------------------------------------------
# AUTH ROUTES: LOGIN, LOGOUT, GANTI PASSWORD
# -------------------------------------------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        user = resolve_user_for_login(username)
        if user and user.check_password(password):
            if not user.is_active:
                flash('Akun dinonaktifkan oleh administrator.', 'danger')
                return render_template('login.html')
            
            session['user_id'] = user.id
            session['role'] = user.role
            flash(f'Selamat datang kembali, {user.nama}!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Username atau kata sandi tidak sesuai. Warga dapat menggunakan kombinasi Nama + No. Rumah (Contoh: AhmadG65 / BudimanG65 / SujatmikoG65).', 'danger')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Anda telah keluar dari sesi Portal RT.', 'info')
    return redirect(url_for('login'))

@app.route('/profil/ganti-password', methods=['GET', 'POST'])
@login_required
def ganti_password():
    user = get_current_user()
    if request.method == 'POST':
        pwd_lama = request.form.get('password_lama', '')
        pwd_baru = request.form.get('password_baru', '')
        pwd_konf = request.form.get('password_konfirmasi', '')

        if not user.check_password(pwd_lama):
            flash('Kata sandi lama yang Anda masukkan tidak tepat.', 'danger')
            return render_template('profil/ganti_password.html', active_page='ganti_password')

        if len(pwd_baru) < 6:
            flash('Kata sandi baru minimal harus 6 karakter.', 'warning')
            return render_template('profil/ganti_password.html', active_page='ganti_password')

        if pwd_baru != pwd_konf:
            flash('Konfirmasi kata sandi baru tidak cocok.', 'warning')
            return render_template('profil/ganti_password.html', active_page='ganti_password')

        user.set_password(pwd_baru)
        db.session.commit()
        flash('Kata sandi berhasil diperbarui dengan aman.', 'success')
        return redirect(url_for('index'))

    return render_template('profil/ganti_password.html', active_page='ganti_password')


# -------------------------------------------------------------
# 1. DASHBOARD (Matching User Screenshot Exactly)
# -------------------------------------------------------------
@app.route('/')
@login_required
def index():
    # 1. Total Kas = Pemasukan - Pengeluaran
    pemasukan = db.session.query(db.func.sum(TransaksiKas.jumlah)).filter_by(jenis='Pemasukan').scalar() or 0.0
    pengeluaran = db.session.query(db.func.sum(TransaksiKas.jumlah)).filter_by(jenis='Pengeluaran').scalar() or 0.0
    total_kas = pemasukan - pengeluaran

    # 2. Ringkasan RT
    total_warga = Warga.query.filter_by(is_aktif=True).count()
    iuran_lunas = Iuran.query.filter_by(status='Lunas').count()
    iuran_belum_lunas = Iuran.query.filter_by(status='Belum Lunas').count()
    iuran_menunggu = Iuran.query.filter_by(status='Menunggu Konfirmasi').count()

    # 3. Pengumuman Aktif
    pengumuman_list = Pengumuman.query.filter_by(is_aktif=True).order_by(Pengumuman.tanggal.desc(), Pengumuman.id.desc()).all()

    # 4. Status Layanan
    pending_surat = Surat.query.filter(Surat.status.in_(['Diajukan', 'Diproses'])).count()
    pending_laporan = Laporan.query.filter(Laporan.status.in_(['Menunggu', 'Diproses'])).count()

    # Indonesian month name
    bulan_dict = {
        1: 'Januari', 2: 'Februari', 3: 'Maret', 4: 'April',
        5: 'Mei', 6: 'Juni', 7: 'Juli', 8: 'Agustus',
        9: 'September', 10: 'Oktober', 11: 'November', 12: 'Desember'
    }
    nama_bulan = bulan_dict.get(datetime.now().month, 'April')

    user = get_current_user()

    # Role-specific counts & metrics
    total_users = User.query.count()
    total_rumah = Rumah.query.count()
    pending_verifikasi_iuran = iuran_menunggu
    active_pinjam_inventaris = PeminjamanInventaris.query.filter_by(status='Dipinjam').count()

    # Personal citizen metrics (for warga or pengurus yang memiliki rumah)
    user_iuran_terbaru = None
    user_iuran_tunggakan = 0
    user_surat_count = 0
    user_surat_disetujui = 0
    user_laporan_count = 0
    user_pinjam_count = 0
    user_rumah = None

    if user and user.warga_id:
        user_iuran_terbaru = Iuran.query.filter_by(warga_id=user.warga_id).order_by(Iuran.periode_tahun.desc(), Iuran.periode_bulan.desc()).first()
        user_iuran_tunggakan = Iuran.query.filter_by(warga_id=user.warga_id, status='Belum Lunas').count()
        user_surat_count = Surat.query.filter_by(warga_id=user.warga_id).count()
        user_surat_disetujui = Surat.query.filter_by(warga_id=user.warga_id, status='Disetujui').count()
        user_laporan_count = Laporan.query.filter_by(warga_id=user.warga_id).count()
        user_pinjam_count = PeminjamanInventaris.query.filter_by(warga_id=user.warga_id, status='Dipinjam').count()
        if user.warga:
            user_rumah = user.warga.rumah_dihuni.first() or user.warga.rumah_dimiliki.first()

    return render_template(
        'dashboard.html',
        active_page='dashboard',
        total_kas=total_kas,
        total_pemasukan=pemasukan,
        total_pengeluaran=pengeluaran,
        total_warga=total_warga,
        iuran_lunas=iuran_lunas,
        iuran_belum_lunas=iuran_belum_lunas,
        iuran_menunggu=iuran_menunggu,
        pengumuman_list=pengumuman_list,
        pending_surat=pending_surat,
        pending_laporan=pending_laporan,
        nama_bulan=nama_bulan,
        total_users=total_users,
        total_rumah=total_rumah,
        pending_verifikasi_iuran=pending_verifikasi_iuran,
        active_pinjam_inventaris=active_pinjam_inventaris,
        user_iuran_terbaru=user_iuran_terbaru,
        user_iuran_tunggakan=user_iuran_tunggakan,
        user_surat_count=user_surat_count,
        user_surat_disetujui=user_surat_disetujui,
        user_laporan_count=user_laporan_count,
        user_pinjam_count=user_pinjam_count,
        user_rumah=user_rumah
    )


# -------------------------------------------------------------
# 2. DATA WARGA
# -------------------------------------------------------------
@app.route('/warga')
@login_required
def warga_index():
    user = get_current_user()

    # If logged in as regular warga: OWN VIEW ONLY!
    if user.role == 'warga':
        if not user.warga:
            flash('Akun Anda belum terhubung dengan data kependudukan RT 09.', 'warning')
            return redirect(url_for('index'))

        # Only display own record & members of the same Kartu Keluarga (KK)
        warga_list = Warga.query.filter_by(no_kk=user.warga.no_kk, is_aktif=True).order_by(Warga.status_keluarga.asc()).all()
        total_warga = len(warga_list)
        total_kk = 1
        total_tetap = sum(1 for w in warga_list if w.status_tinggal == 'Tetap')
        total_kontrak = total_warga - total_tetap

        return render_template(
            'warga/index.html',
            active_page='warga',
            warga_list=warga_list,
            total_warga=total_warga,
            total_kk=total_kk,
            total_tetap=total_tetap,
            total_kontrak=total_kontrak,
            is_own_view=True
        )

    # For Admin, Pengurus, Pejabat: View all citizens with search & filter
    query = Warga.query.filter_by(is_aktif=True)

    # Search
    q = request.args.get('q', '').strip()
    if q:
        query = query.filter(
            (Warga.nama.ilike(f'%{q}%')) |
            (Warga.nik.ilike(f'%{q}%')) |
            (Warga.no_kk.ilike(f'%{q}%')) |
            (Warga.no_rumah.ilike(f'%{q}%'))
        )

    # Filter status tinggal
    st_tinggal = request.args.get('status_tinggal', '').strip()
    if st_tinggal:
        query = query.filter_by(status_tinggal=st_tinggal)

    # Filter status keluarga
    st_kel = request.args.get('status_keluarga', '').strip()
    if st_kel:
        query = query.filter_by(status_keluarga=st_kel)

    warga_list = query.order_by(Warga.no_rumah.asc(), Warga.nama.asc()).all()

    total_warga = Warga.query.filter_by(is_aktif=True).count()
    total_kk = Warga.query.filter_by(is_aktif=True, status_keluarga='Kepala Keluarga').count()
    total_tetap = Warga.query.filter_by(is_aktif=True, status_tinggal='Tetap').count()
    total_kontrak = Warga.query.filter(Warga.is_aktif == True, Warga.status_tinggal.in_(['Kontrak', 'Kost'])).count()

    return render_template(
        'warga/index.html',
        active_page='warga',
        warga_list=warga_list,
        total_warga=total_warga,
        total_kk=total_kk,
        total_tetap=total_tetap,
        total_kontrak=total_kontrak,
        is_own_view=False
    )

@app.route('/warga/tambah', methods=['GET', 'POST'])
@login_required
@admin_required
def warga_tambah():
    if request.method == 'POST':
        nik = request.form.get('nik', '').strip()
        no_kk = request.form.get('no_kk', '').strip()
        nama = request.form.get('nama', '').strip()
        
        # Check duplicate NIK
        if Warga.query.filter_by(nik=nik).first():
            flash(f'NIK {nik} sudah terdaftar di sistem!', 'danger')
            return render_template('warga/form.html', active_page='warga', warga=None)

        tgl_lahir = None
        tgl_str = request.form.get('tanggal_lahir')
        if tgl_str:
            try:
                tgl_lahir = datetime.strptime(tgl_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        w = Warga(
            nik=nik,
            no_kk=no_kk,
            nama=nama,
            jenis_kelamin=request.form.get('jenis_kelamin', 'Laki-laki'),
            tempat_lahir=request.form.get('tempat_lahir', ''),
            tanggal_lahir=tgl_lahir,
            agama=request.form.get('agama', 'Islam'),
            pekerjaan=request.form.get('pekerjaan', ''),
            status_perkawinan=request.form.get('status_perkawinan', 'Kawin'),
            status_keluarga=request.form.get('status_keluarga', 'Kepala Keluarga'),
            status_tinggal=request.form.get('status_tinggal', 'Tetap'),
            no_rumah=request.form.get('no_rumah', ''),
            alamat=request.form.get('alamat', ''),
            rt_rw='09/14',
            no_hp=request.form.get('no_hp', ''),
            email=request.form.get('email', '')
        )
        db.session.add(w)
        db.session.commit()
        flash(f'Data warga {nama} berhasil ditambahkan ke basis data RT 09.', 'success')
        return redirect(url_for('warga_index'))

    return render_template('warga/form.html', active_page='warga', warga=None, is_warga_edit=False)

@app.route('/warga/<int:id>')
@login_required
def warga_detail(id):
    user = get_current_user()
    warga = Warga.query.get_or_404(id)

    # OWN VIEW check for warga
    if user.role == 'warga':
        if not user.warga or (warga.id != user.warga_id and warga.no_kk != user.warga.no_kk):
            flash('Akses ditolak. Anda hanya berhak melihat profil Anda sendiri atau keluarga Anda.', 'danger')
            return redirect(url_for('warga_index'))

    # Get members of the same family / KK
    keluarga_list = Warga.query.filter_by(no_kk=warga.no_kk, is_aktif=True).all()
    # Recent dues
    recent_iuran = Iuran.query.filter_by(warga_id=warga.id).order_by(Iuran.periode_tahun.desc(), Iuran.periode_bulan.desc()).limit(6).all()
    
    can_edit = user.is_admin() or (user.warga_id == warga.id or (user.warga and user.warga.no_kk == warga.no_kk))

    return render_template(
        'warga/detail.html',
        active_page='warga',
        warga=warga,
        keluarga_list=keluarga_list,
        recent_iuran=recent_iuran,
        can_edit=can_edit
    )

@app.route('/warga/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def warga_edit(id):
    user = get_current_user()
    w = Warga.query.get_or_404(id)

    # OWN EDIT check: warga can ONLY edit themselves or their family in same KK
    if user.role == 'warga':
        if not user.warga or (w.id != user.warga_id and w.no_kk != user.warga.no_kk):
            flash('Akses ditolak. Anda hanya berhak mengubah data Anda sendiri atau anggota keluarga Anda.', 'danger')
            return redirect(url_for('warga_index'))

    if request.method == 'POST':
        # Admin can modify NIK, No KK, and status fields; warga keeps official NIK/KK intact
        if user.is_admin():
            w.nik = request.form.get('nik', w.nik).strip()
            w.no_kk = request.form.get('no_kk', w.no_kk).strip()
            w.status_keluarga = request.form.get('status_keluarga', w.status_keluarga)
            w.status_tinggal = request.form.get('status_tinggal', w.status_tinggal)

        w.nama = request.form.get('nama', w.nama).strip()
        w.jenis_kelamin = request.form.get('jenis_kelamin', w.jenis_kelamin)
        w.tempat_lahir = request.form.get('tempat_lahir', '')
        tgl_str = request.form.get('tanggal_lahir')
        if tgl_str:
            try:
                w.tanggal_lahir = datetime.strptime(tgl_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        w.agama = request.form.get('agama', w.agama)
        w.pekerjaan = request.form.get('pekerjaan', '')
        w.status_perkawinan = request.form.get('status_perkawinan', w.status_perkawinan)
        w.no_rumah = request.form.get('no_rumah', w.no_rumah)
        w.alamat = request.form.get('alamat', w.alamat)
        w.no_hp = request.form.get('no_hp', w.no_hp)
        w.email = request.form.get('email', w.email)

        db.session.commit()
        flash(f'Perubahan data warga {w.nama} berhasil disimpan.', 'success')
        return redirect(url_for('warga_detail', id=w.id))

    return render_template(
        'warga/form.html',
        active_page='warga',
        warga=w,
        is_warga_edit=(user.role == 'warga')
    )

@app.route('/warga/hapus/<int:id>', methods=['POST'])
@login_required
@admin_required
def warga_hapus(id):
    w = Warga.query.get_or_404(id)
    nama = w.nama
    db.session.delete(w)
    db.session.commit()
    flash(f'Data warga {nama} telah dihapus dari sistem.', 'info')
    return redirect(url_for('warga_index'))

@app.route('/warga/export')
@login_required
def warga_export():
    warga_list = Warga.query.filter_by(is_aktif=True).order_by(Warga.no_rumah.asc()).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['NIK', 'No KK', 'Nama Lengkap', 'Jenis Kelamin', 'Tempat Lahir', 'Tanggal Lahir', 'Agama', 'Pekerjaan', 'Status Perkawinan', 'Status Keluarga', 'Status Tinggal', 'No Rumah', 'Alamat', 'No HP', 'Email'])
    
    for w in warga_list:
        writer.writerow([
            f"'{w.nik}", f"'{w.no_kk}", w.nama, w.jenis_kelamin, w.tempat_lahir,
            w.tanggal_lahir.strftime('%Y-%m-%d') if w.tanggal_lahir else '',
            w.agama, w.pekerjaan, w.status_perkawinan, w.status_keluarga,
            w.status_tinggal, w.no_rumah, w.alamat, w.no_hp, w.email
        ])

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={"Content-disposition": "attachment; filename=data_warga_rt09.csv"}
    )


# -------------------------------------------------------------
# 2.1 RUMAH & KETERHUNIAN (DUAL-KEY PROPERTY LEDGER)
# -------------------------------------------------------------
@app.route('/rumah')
@login_required
def rumah_index():
    user = get_current_user()
    
    # Regular warga can see:
    # 1. House they currently occupy (penghuni_aktif_id == user.warga_id)
    # 2. House they own (pemilik_id == user.warga_id)
    if user.role == 'warga':
        if not user.warga_id:
            rumah_list = []
        else:
            w_obj = user.warga
            no_rmh = w_obj.no_rumah if w_obj else ''
            rumah_list = Rumah.query.filter(
                (Rumah.penghuni_aktif_id == user.warga_id) |
                (Rumah.pemilik_id == user.warga_id) |
                (Rumah.no_rumah == no_rmh)
            ).order_by(Rumah.no_rumah.asc()).all()
        is_own_view = True
    else:
        # Admin / Pengurus / Pejabat: View all houses with search and filter
        query = Rumah.query
        q = request.args.get('q', '').strip()
        if q:
            query = query.filter(
                (Rumah.no_rumah.ilike(f'%{q}%')) |
                (Rumah.blok.ilike(f'%{q}%')) |
                (Rumah.nomor.ilike(f'%{q}%')) |
                (Rumah.alamat.ilike(f'%{q}%'))
            )
        
        status_huni = request.args.get('status_huni', '').strip()
        if status_huni:
            query = query.filter_by(status_huni=status_huni)
            
        tipe_penghuni = request.args.get('tipe_penghuni', '').strip()
        if tipe_penghuni:
            query = query.filter_by(tipe_penghuni=tipe_penghuni)

        rumah_list = query.order_by(Rumah.no_rumah.asc()).all()
        is_own_view = False

    total_rumah = Rumah.query.count()
    dihuni_pemilik = Rumah.query.filter_by(status_huni='Dihuni Pemilik').count()
    dikontrakkan = Rumah.query.filter_by(status_huni='Dikontrakkan').count()
    kosong = Rumah.query.filter_by(status_huni='Kosong').count()

    return render_template(
        'rumah/index.html',
        active_page='rumah',
        rumah_list=rumah_list,
        total_rumah=total_rumah,
        dihuni_pemilik=dihuni_pemilik,
        dikontrakkan=dikontrakkan,
        kosong=kosong,
        is_own_view=is_own_view
    )

@app.route('/rumah/<int:id>')
@login_required
def rumah_detail(id):
    user = get_current_user()
    rumah = Rumah.query.get_or_404(id)

    # Permission check for regular warga
    if user.role == 'warga':
        w_obj = user.warga
        no_rmh = w_obj.no_rumah if w_obj else ''
        if not user.warga_id or (rumah.penghuni_aktif_id != user.warga_id and rumah.pemilik_id != user.warga_id and rumah.no_rumah != no_rmh):
            flash('Akses ditolak. Anda hanya berhak mengakses buku besar rumah yang Anda huni atau miliki.', 'danger')
            return redirect(url_for('rumah_index'))

    # Continuous Ledger of Iuran for this house
    # Order descending by period
    iuran_records = Iuran.query.filter_by(rumah_id=rumah.id).order_by(Iuran.periode_tahun.desc(), Iuran.periode_bulan.desc()).all()
    
    # Calculate ledger summary for this house
    total_tagihan = len(iuran_records)
    total_lunas = sum(1 for i in iuran_records if i.status == 'Lunas')
    total_tunggakan = sum(1 for i in iuran_records if i.status == 'Belum Lunas')
    nominal_lunas = sum(i.jumlah for i in iuran_records if i.status == 'Lunas')
    nominal_tunggakan = sum(i.jumlah for i in iuran_records if i.status == 'Belum Lunas')

    # Tenancy history timeline
    timeline = RiwayatKeterhunian.query.filter_by(rumah_id=rumah.id).order_by(RiwayatKeterhunian.tgl_mulai.desc()).all()

    can_manage = user.is_admin() or (rumah.pemilik_id == user.warga_id)

    return render_template(
        'rumah/detail.html',
        active_page='rumah',
        rumah=rumah,
        iuran_records=iuran_records,
        timeline=timeline,
        total_tagihan=total_tagihan,
        total_lunas=total_lunas,
        total_tunggakan=total_tunggakan,
        nominal_lunas=nominal_lunas,
        nominal_tunggakan=nominal_tunggakan,
        can_manage=can_manage
    )

@app.route('/rumah/tambah', methods=['GET', 'POST'])
@login_required
@admin_required
def rumah_tambah():
    if request.method == 'POST':
        no_rumah = request.form.get('no_rumah', '').strip()
        blok = request.form.get('blok', '').strip()
        nomor = request.form.get('nomor', '').strip()
        alamat = request.form.get('alamat', '').strip()
        pemilik_id = request.form.get('pemilik_id') or None
        penghuni_aktif_id = request.form.get('penghuni_aktif_id') or None
        status_huni = request.form.get('status_huni', 'Dihuni Pemilik')
        tipe_penghuni = request.form.get('tipe_penghuni', 'Pemilik')
        catatan = request.form.get('catatan', '')

        if Rumah.query.filter_by(no_rumah=no_rumah).first():
            flash(f'Rumah dengan nomor {no_rumah} sudah terdaftar!', 'danger')
            return redirect(url_for('rumah_tambah'))

        r = Rumah(
            no_rumah=no_rumah,
            blok=blok,
            nomor=nomor,
            alamat=alamat,
            pemilik_id=int(pemilik_id) if pemilik_id else None,
            penghuni_aktif_id=int(penghuni_aktif_id) if penghuni_aktif_id else None,
            status_huni=status_huni,
            tipe_penghuni=tipe_penghuni,
            catatan=catatan
        )
        db.session.add(r)
        db.session.flush()

        # Log initial occupancy
        if r.penghuni_aktif_id:
            log = RiwayatKeterhunian(
                rumah_id=r.id,
                warga_id=r.penghuni_aktif_id,
                tipe_penghuni=r.tipe_penghuni,
                tgl_mulai=date.today(),
                is_aktif=True,
                status_tunggakan='Lunas',
                catatan_serah_terima='Pendaftaran data unit rumah baru'
            )
            db.session.add(log)

        db.session.commit()
        flash(f'Unit rumah {no_rumah} berhasil didaftarkan.', 'success')
        return redirect(url_for('rumah_detail', id=r.id))

    warga_list = Warga.query.filter_by(is_aktif=True).order_by(Warga.nama.asc()).all()
    return render_template('rumah/form.html', active_page='rumah', rumah=None, warga_list=warga_list)

@app.route('/rumah/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def rumah_edit(id):
    r = Rumah.query.get_or_404(id)
    if request.method == 'POST':
        r.blok = request.form.get('blok', r.blok).strip()
        r.nomor = request.form.get('nomor', r.nomor).strip()
        r.no_rumah = request.form.get('no_rumah', r.no_rumah).strip()
        r.alamat = request.form.get('alamat', r.alamat).strip()
        
        pemilik_id = request.form.get('pemilik_id')
        r.pemilik_id = int(pemilik_id) if pemilik_id else None
        
        r.status_huni = request.form.get('status_huni', r.status_huni)
        r.tipe_penghuni = request.form.get('tipe_penghuni', r.tipe_penghuni)
        r.catatan = request.form.get('catatan', r.catatan)
        
        db.session.commit()
        flash(f'Data rumah {r.no_rumah} berhasil diperbarui.', 'success')
        return redirect(url_for('rumah_detail', id=r.id))

    warga_list = Warga.query.filter_by(is_aktif=True).order_by(Warga.nama.asc()).all()
    return render_template('rumah/form.html', active_page='rumah', rumah=r, warga_list=warga_list)

@app.route('/rumah/serah-terima/<int:id>', methods=['GET', 'POST'])
@login_required
def rumah_serah_terima(id):
    user = get_current_user()
    r = Rumah.query.get_or_404(id)

    # Only admin or property owner can perform tenancy handover
    if not user.is_admin() and r.pemilik_id != user.warga_id:
        flash('Akses ditolak. Serah terima keterhunian hanya dapat dilakukan oleh Pengurus RT atau Pemilik Rumah.', 'danger')
        return redirect(url_for('rumah_detail', id=r.id))

    # Check outstanding dues of current occupant
    tunggakan_lama = []
    if r.penghuni_aktif_id:
        tunggakan_lama = Iuran.query.filter_by(
            rumah_id=r.id, 
            warga_id=r.penghuni_aktif_id, 
            status='Belum Lunas'
        ).all()

    if request.method == 'POST':
        action_type = request.form.get('action_type', 'ganti_penghuni') # 'ganti_penghuni', 'kembali_ke_pemilik', 'kosongkan'
        new_warga_id = request.form.get('new_warga_id')
        tgl_serah_terima_str = request.form.get('tgl_serah_terima')
        catatan_serah_terima = request.form.get('catatan_serah_terima', '').strip()
        status_tunggakan = request.form.get('status_tunggakan', 'Lunas' if not tunggakan_lama else 'Ada Tunggakan')

        tgl_serah_terima = date.today()
        if tgl_serah_terima_str:
            try:
                tgl_serah_terima = datetime.strptime(tgl_serah_terima_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        # 1. Close current active RiwayatKeterhunian
        active_log = RiwayatKeterhunian.query.filter_by(rumah_id=r.id, is_aktif=True).first()
        if active_log:
            active_log.is_aktif = False
            active_log.tgl_selesai = tgl_serah_terima
            active_log.status_tunggakan = status_tunggakan
            if catatan_serah_terima:
                active_log.catatan_serah_terima = f"{active_log.catatan_serah_terima or ''} | Pengakhiran: {catatan_serah_terima}".strip(' |')

        # 2. Determine new resident & status
        if action_type == 'kosongkan':
            r.penghuni_aktif_id = None
            r.status_huni = 'Kosong'
            r.tipe_penghuni = 'Kosong'
            msg = f'Unit rumah {r.no_rumah} kini berstatus KOSONG. Riwayat keterhunian sebelumnya tersimpan rapi.'
        elif action_type == 'kembali_ke_pemilik':
            r.penghuni_aktif_id = r.pemilik_id
            r.status_huni = 'Dihuni Pemilik'
            r.tipe_penghuni = 'Pemilik'
            # Start new log for owner
            if r.pemilik_id:
                new_log = RiwayatKeterhunian(
                    rumah_id=r.id,
                    warga_id=r.pemilik_id,
                    tipe_penghuni='Pemilik',
                    tgl_mulai=tgl_serah_terima,
                    is_aktif=True,
                    status_tunggakan='Lunas',
                    catatan_serah_terima=f"Kembali dihuni oleh pemilik sah. {catatan_serah_terima}"
                )
                db.session.add(new_log)
            msg = f'Unit rumah {r.no_rumah} berhasil diserah-terimakan kembali kepada PEMILIK. Iuran selanjutnya menjadi tanggung jawab pemilik.'
        else: # 'ganti_penghuni'
            target_warga_id = int(new_warga_id) if new_warga_id else None
            tipe_baru = request.form.get('tipe_penghuni_baru', 'Pengontrak')
            r.penghuni_aktif_id = target_warga_id
            r.status_huni = 'Dikontrakkan' if tipe_baru == 'Pengontrak' else 'Dihuni Pemilik'
            r.tipe_penghuni = tipe_baru

            # Start new log for new resident
            if target_warga_id:
                new_log = RiwayatKeterhunian(
                    rumah_id=r.id,
                    warga_id=target_warga_id,
                    tipe_penghuni=tipe_baru,
                    tgl_mulai=tgl_serah_terima,
                    is_aktif=True,
                    status_tunggakan='Lunas',
                    catatan_serah_terima=f"Mulai masa huni baru. {catatan_serah_terima}"
                )
                db.session.add(new_log)
            msg = f'Pergantian penghuni rumah {r.no_rumah} berhasil dicatat. Penanggung jawab iuran aktif telah dialihkan.'

        db.session.commit()
        flash(msg, 'success')
        return redirect(url_for('rumah_detail', id=r.id))

    warga_list = Warga.query.filter_by(is_aktif=True).order_by(Warga.nama.asc()).all()
    return render_template(
        'rumah/serah_terima.html',
        active_page='rumah',
        rumah=r,
        tunggakan_lama=tunggakan_lama,
        warga_list=warga_list,
        today=date.today()
    )


# -------------------------------------------------------------
# 3. IURAN WARGA
# -------------------------------------------------------------
@app.route('/iuran')
@login_required
def iuran_index():
    user = get_current_user()
    query = Iuran.query.join(Warga)

    # View Mode: 'semua' (seluruh warga) or 'saya' (iuran pribadi pengguna yang login)
    # Catatan: Superadmin BUKAN warga (warga_id=None), sehingga selalu melihat mode 'semua'
    if user.is_superadmin():
        view_mode = 'semua'
        is_own_filter = False
    else:
        view_mode = request.args.get('view', 'saya' if user.role == 'warga' else 'semua')
        is_own_filter = (user.role == 'warga' or view_mode == 'saya')

    if is_own_filter:
        if user.warga_id:
            query = query.filter(Iuran.warga_id == user.warga_id)
        else:
            query = query.filter(Iuran.warga_id == -1)

    # Filters
    bulan = request.args.get('bulan', '')
    if bulan:
        query = query.filter(Iuran.periode_bulan == int(bulan))

    tahun = request.args.get('tahun', '2026')
    if tahun:
        query = query.filter(Iuran.periode_tahun == int(tahun))

    status = request.args.get('status', '')
    if status:
        query = query.filter(Iuran.status == status)

    q = request.args.get('q', '').strip()
    if q and not is_own_filter:
        query = query.filter((Warga.nama.ilike(f'%{q}%')) | (Warga.nik.ilike(f'%{q}%')))

    iuran_list = query.order_by(Iuran.periode_tahun.desc(), Iuran.periode_bulan.desc(), Warga.nama.asc()).all()

    # Base counts for widgets
    base_q = Iuran.query
    if is_own_filter:
        if user.warga_id:
            base_q = base_q.filter_by(warga_id=user.warga_id)

    total_tagihan = base_q.count()
    lunas_count = base_q.filter_by(status='Lunas').count()
    lunas_total = db.session.query(db.func.sum(Iuran.jumlah)).filter_by(status='Lunas')
    if is_own_filter and user.warga_id:
        lunas_total = lunas_total.filter_by(warga_id=user.warga_id)
    lunas_total = lunas_total.scalar() or 0.0

    belum_count = base_q.filter_by(status='Belum Lunas').count()
    belum_total = db.session.query(db.func.sum(Iuran.jumlah)).filter_by(status='Belum Lunas')
    if is_own_filter and user.warga_id:
        belum_total = belum_total.filter_by(warga_id=user.warga_id)
    belum_total = belum_total.scalar() or 0.0

    menunggu_count = base_q.filter_by(status='Menunggu Konfirmasi').count()

    return render_template(
        'iuran/index.html',
        active_page='iuran',
        iuran_list=iuran_list,
        total_tagihan=total_tagihan,
        lunas_count=lunas_count,
        lunas_total=lunas_total,
        belum_count=belum_count,
        belum_total=belum_total,
        menunggu_count=menunggu_count,
        view_mode=view_mode
    )

@app.route('/iuran/bayar/<int:id>', methods=['POST'])
@login_required
def iuran_bayar(id):
    iur = Iuran.query.get_or_404(id)
    metode = request.form.get('metode_bayar', 'QRIS')
    catatan = request.form.get('catatan', '')

    bukti_filename = None
    if 'bukti_transfer' in request.files:
        f = request.files['bukti_transfer']
        if f and f.filename != '':
            ext = os.path.splitext(f.filename)[1]
            fname = f"bukti_{iur.id}_{int(datetime.utcnow().timestamp())}{ext}"
            f.save(os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(fname)))
            bukti_filename = fname

    user = get_current_user()
    if user.is_admin():
        # If admin records payment, immediately mark as Lunas!
        iur.status = 'Lunas'
        iur.metode_bayar = metode
        iur.tanggal_bayar = datetime.utcnow()
        iur.verified_by = user.nama
        iur.verified_at = datetime.utcnow()
        if bukti_filename:
            iur.bukti_transfer = bukti_filename
        if catatan:
            iur.catatan = catatan

        # Create Kas Transaction record
        trx = TransaksiKas(
            kode_transaksi=f"TRX-IUR-{iur.id}-{int(datetime.utcnow().timestamp()) % 10000}",
            jenis='Pemasukan',
            kategori='Iuran Warga',
            judul=f"Iuran Bulan {iur.periode_bulan}/{iur.periode_tahun} - {iur.warga.nama}",
            jumlah=iur.jumlah,
            tanggal=date.today(),
            keterangan=f"Pembayaran melalui {metode}. Catatan: {catatan}",
            iuran_id=iur.id,
            created_by=user.nama
        )
        db.session.add(trx)
        flash('Pembayaran iuran berhasil dicatat dan diverifikasi LUNAS.', 'success')
    else:
        # Resident submits payment for confirmation
        iur.status = 'Menunggu Konfirmasi'
        iur.metode_bayar = metode
        iur.tanggal_bayar = datetime.utcnow()
        if bukti_filename:
            iur.bukti_transfer = bukti_filename
        if catatan:
            iur.catatan = catatan
        flash('Bukti pembayaran Anda berhasil dikirim dan sedang menunggu verifikasi Bendahara RT.', 'info')

    db.session.commit()
    return redirect(url_for('iuran_index'))

@app.route('/iuran/verifikasi/<int:id>', methods=['POST'])
@login_required
@admin_required
def iuran_verifikasi(id):
    iur = Iuran.query.get_or_404(id)
    user = get_current_user()

    iur.status = 'Lunas'
    iur.verified_by = user.nama
    iur.verified_at = datetime.utcnow()
    if not iur.tanggal_bayar:
        iur.tanggal_bayar = datetime.utcnow()

    # Automatically add to Transaksi Kas if not already recorded
    if not TransaksiKas.query.filter_by(iuran_id=iur.id).first():
        trx = TransaksiKas(
            kode_transaksi=f"TRX-IUR-{iur.id}-{int(datetime.utcnow().timestamp()) % 10000}",
            jenis='Pemasukan',
            kategori='Iuran Warga',
            judul=f"Iuran Bulan {iur.periode_bulan}/{iur.periode_tahun} - {iur.warga.nama}",
            jumlah=iur.jumlah,
            tanggal=date.today(),
            keterangan=f"Verifikasi pembayaran oleh {user.nama}",
            iuran_id=iur.id,
            created_by=user.nama
        )
        db.session.add(trx)

    db.session.commit()
    flash(f'Iuran warga {iur.warga.nama} periode {iur.periode_bulan}/{iur.periode_tahun} diverifikasi LUNAS.', 'success')
    return redirect(url_for('iuran_index'))

@app.route('/iuran/bayar-batch', methods=['POST'])
@login_required
def iuran_bayar_batch():
    user = get_current_user()
    
    # Ambil list ID iuran yang dipilih
    raw_ids = request.form.getlist('iuran_ids')
    if not raw_ids and request.form.get('batch_iuran_ids'):
        raw_ids = [x.strip() for x in request.form.get('batch_iuran_ids').split(',') if x.strip()]
    
    try:
        iuran_ids = [int(x) for x in raw_ids if str(x).isdigit()]
    except Exception:
        iuran_ids = []

    if not iuran_ids:
        flash('Silakan pilih minimal satu tagihan iuran untuk diproses.', 'warning')
        return redirect(url_for('iuran_index'))

    # Ambil data iuran dari database
    iurans = Iuran.query.filter(Iuran.id.in_(iuran_ids)).order_by(Iuran.periode_tahun.asc(), Iuran.periode_bulan.asc()).all()
    if not iurans:
        flash('Data tagihan yang dipilih tidak ditemukan.', 'danger')
        return redirect(url_for('iuran_index'))

    # Hak Akses: warga hanya boleh memproses iuran keluarga sendiri
    if not user.is_admin():
        for iur in iurans:
            if not user.warga_id or user.warga_id != iur.warga_id:
                flash('Akses ditolak. Anda hanya berhak memproses iuran keluarga Anda sendiri.', 'danger')
                return redirect(url_for('iuran_index'))

    metode = request.form.get('metode_bayar', 'Transfer Bank')
    catatan = request.form.get('catatan', '').strip()

    # Upload bukti transfer (berlaku untuk semua baris dalam transaksi sekaligus ini)
    bukti_filename = None
    if 'bukti_transfer' in request.files:
        f = request.files['bukti_transfer']
        if f and f.filename != '':
            ext = os.path.splitext(f.filename)[1]
            fname = f"bukti_batch_{int(datetime.utcnow().timestamp())}{ext}"
            f.save(os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(fname)))
            bukti_filename = fname

    batch_code = f"BATCH-{datetime.utcnow().strftime('%Y%m%d%H%M')}-{int(datetime.utcnow().timestamp()) % 10000}"
    total_jumlah = sum(x.jumlah for x in iurans)
    
    periode_list = [f"{x.periode_bulan}/{x.periode_tahun}" for x in iurans]
    periode_ringkas = ", ".join(periode_list) if len(periode_list) <= 4 else f"{periode_list[0]} s/d {periode_list[-1]} ({len(iurans)} Bulan)"
    first_warga = iurans[0].warga.nama if iurans and iurans[0].warga else "Warga"

    now = datetime.utcnow()
    if user.is_admin():
        for iur in iurans:
            iur.status = 'Lunas'
            iur.metode_bayar = metode
            iur.tanggal_bayar = now
            iur.verified_by = user.nama
            iur.verified_at = now
            iur.kode_pembayaran = batch_code
            if bukti_filename:
                iur.bukti_transfer = bukti_filename
            if catatan:
                iur.catatan = catatan

        # Catat 1 baris Transaksi Kas Gabungan untuk seluruh bulan yang dibayar
        trx = TransaksiKas(
            kode_transaksi=f"TRX-IUR-{batch_code}",
            jenis='Pemasukan',
            kategori='Iuran Warga',
            judul=f"Iuran ({len(iurans)} Bulan: {periode_ringkas}) - {first_warga}",
            jumlah=total_jumlah,
            tanggal=date.today(),
            keterangan=f"Pembayaran {len(iurans)} bulan sekaligus via {metode}. Kode: {batch_code}. {catatan}".strip(),
            iuran_id=iurans[0].id,
            created_by=user.nama
        )
        db.session.add(trx)
        flash(f'Pembayaran {len(iurans)} bulan iuran ({first_warga}) berhasil dicatat LUNAS. Total: Rp {total_jumlah:,.0f}.', 'success')
    else:
        for iur in iurans:
            iur.status = 'Menunggu Konfirmasi'
            iur.metode_bayar = metode
            iur.tanggal_bayar = now
            iur.kode_pembayaran = batch_code
            if bukti_filename:
                iur.bukti_transfer = bukti_filename
            if catatan:
                iur.catatan = catatan

        flash(f'Bukti pembayaran {len(iurans)} bulan iuran berhasil dikirim (Total: Rp {total_jumlah:,.0f}). Menunggu verifikasi Bendahara RT.', 'info')

    db.session.commit()
    return redirect(url_for('iuran_index'))

@app.route('/iuran/verifikasi-batch', methods=['POST'])
@login_required
@admin_required
def iuran_verifikasi_batch():
    user = get_current_user()
    raw_ids = request.form.getlist('iuran_ids')
    if not raw_ids and request.form.get('batch_iuran_ids'):
        raw_ids = [x.strip() for x in request.form.get('batch_iuran_ids').split(',') if x.strip()]

    try:
        iuran_ids = [int(x) for x in raw_ids if str(x).isdigit()]
    except Exception:
        iuran_ids = []

    if not iuran_ids:
        flash('Silakan pilih minimal satu tagihan iuran untuk diverifikasi.', 'warning')
        return redirect(url_for('iuran_index'))

    iurans = Iuran.query.filter(Iuran.id.in_(iuran_ids), Iuran.status != 'Lunas').all()
    if not iurans:
        flash('Tidak ada tagihan tertunda yang perlu diverifikasi pada pilihan Anda.', 'info')
        return redirect(url_for('iuran_index'))

    now = datetime.utcnow()
    count_verified = 0
    total_nominal = 0

    for iur in iurans:
        iur.status = 'Lunas'
        iur.verified_by = user.nama
        iur.verified_at = now
        if not iur.tanggal_bayar:
            iur.tanggal_bayar = now
        count_verified += 1
        total_nominal += iur.jumlah

        # Jika belum ada pencatatan kas untuk iuran ini
        if not TransaksiKas.query.filter_by(iuran_id=iur.id).first():
            trx = TransaksiKas(
                kode_transaksi=f"TRX-IUR-{iur.id}-{int(now.timestamp()) % 10000}",
                jenis='Pemasukan',
                kategori='Iuran Warga',
                judul=f"Iuran Bulan {iur.periode_bulan}/{iur.periode_tahun} - {iur.warga.nama}",
                jumlah=iur.jumlah,
                tanggal=date.today(),
                keterangan=f"Verifikasi massal oleh {user.nama}",
                iuran_id=iur.id,
                created_by=user.nama
            )
            db.session.add(trx)

    db.session.commit()
    flash(f'Berhasil memverifikasi {count_verified} tagihan iuran menjadi LUNAS (Total: Rp {total_nominal:,.0f}).', 'success')
    return redirect(url_for('iuran_index'))

@app.route('/iuran/generate', methods=['POST'])
@login_required
@admin_required
def iuran_generate_periode():
    bulan = int(request.form.get('bulan', 5))
    tahun = int(request.form.get('tahun', 2026))
    nominal = float(Pengaturan.get('iuran_bulanan', 15000))

    warga_list = Warga.query.filter_by(is_aktif=True).all()
    created_count = 0
    for w in warga_list:
        existing = Iuran.query.filter_by(warga_id=w.id, periode_bulan=bulan, periode_tahun=tahun).first()
        if not existing:
            iur = Iuran(
                warga_id=w.id,
                periode_bulan=bulan,
                periode_tahun=tahun,
                jumlah=nominal,
                status='Belum Lunas'
            )
            db.session.add(iur)
            created_count += 1

    db.session.commit()
    flash(f'Berhasil membuat {created_count} tagihan iuran baru untuk periode {bulan}/{tahun}.', 'success')
    return redirect(url_for('iuran_index', bulan=bulan, tahun=tahun))

@app.route('/iuran/warga/<int:warga_id>')
@login_required
def iuran_warga_detail(warga_id):
    warga = Warga.query.get_or_404(warga_id)
    iuran_list = Iuran.query.filter_by(warga_id=warga.id).order_by(Iuran.periode_tahun.desc(), Iuran.periode_bulan.desc()).all()
    return render_template('iuran/index.html', active_page='iuran', iuran_list=iuran_list, total_tagihan=len(iuran_list), lunas_count=sum(1 for x in iuran_list if x.status == 'Lunas'), lunas_total=sum(x.jumlah for x in iuran_list if x.status == 'Lunas'), belum_count=sum(1 for x in iuran_list if x.status == 'Belum Lunas'), belum_total=sum(x.jumlah for x in iuran_list if x.status == 'Belum Lunas'), menunggu_count=sum(1 for x in iuran_list if x.status == 'Menunggu Konfirmasi'))

@app.route('/iuran/kuitansi/<int:id>')
@login_required
def iuran_kuitansi(id):
    iur = Iuran.query.get_or_404(id)
    user = get_current_user()

    # Access control: Warga hanya boleh mencetak kuitansi miliknya
    if not user.is_admin():
        if not user.warga_id or user.warga_id != iur.warga_id:
            flash('Akses ditolak. Anda hanya berhak mencetak kuitansi iuran keluarga Anda.', 'danger')
            return redirect(url_for('iuran_index'))

    settings = {s.kunci: s.nilai for s in Pengaturan.query.all()}
    nama_rt = settings.get('nama_rt', 'RT 09')
    nama_rw = settings.get('nama_rw', 'RW 14')
    kelurahan = settings.get('kelurahan', 'Mojosarirejo')
    kecamatan = settings.get('kecamatan', 'Driyorejo')
    kota = settings.get('kota', 'Jawa Timur')
    kode_pos = settings.get('kode_pos', '13790')
    nama_ketua = settings.get('nama_ketua_rt', 'H. Bambang Sutrisno')
    no_hp_rt = settings.get('no_hp_rt', '0812-3456-7890')
    qris_merchant = settings.get('qris_merchant_name', 'KAS PAGUYUBAN RT 09')

    # Cek apakah bagian dari pembayaran batch sekaligus
    batch_items = []
    if iur.kode_pembayaran:
        batch_items = Iuran.query.filter_by(kode_pembayaran=iur.kode_pembayaran).order_by(Iuran.periode_tahun.asc(), Iuran.periode_bulan.asc()).all()
    if not batch_items:
        batch_items = [iur]

    total_jumlah = sum(x.jumlah for x in batch_items)
    terbilang_str = terbilang_rupiah(total_jumlah)

    if len(batch_items) > 1:
        no_kuitansi = f"KWT/{nama_rt.replace(' ', '')}/BATCH/{str(iur.id).zfill(4)}"
    else:
        no_kuitansi = f"KWT/{nama_rt.replace(' ', '')}/{iur.periode_tahun}/{str(iur.periode_bulan).zfill(2)}/{str(iur.id).zfill(4)}"

    # Tanggal cetak & tgl lunas
    tgl_lunas_str = iur.tanggal_bayar.strftime('%d %B %Y') if iur.tanggal_bayar else (iur.verified_at.strftime('%d %B %Y') if iur.verified_at else date.today().strftime('%d %B %Y'))

    return render_template(
        'iuran/kuitansi.html',
        iur=iur,
        batch_items=batch_items,
        total_jumlah=total_jumlah,
        no_kuitansi=no_kuitansi,
        terbilang=terbilang_str,
        tgl_lunas_str=tgl_lunas_str,
        nama_rt=nama_rt,
        nama_rw=nama_rw,
        kelurahan=kelurahan,
        kecamatan=kecamatan,
        kota=kota,
        kode_pos=kode_pos,
        nama_ketua=nama_ketua,
        no_hp_rt=no_hp_rt,
        qris_merchant=qris_merchant,
        now_str=date.today().strftime('%d %B %Y')
    )


# -------------------------------------------------------------
# 4. TRANSAKSI KAS
# -------------------------------------------------------------
@app.route('/kas')
@login_required
def kas_index():
    query = TransaksiKas.query

    jenis = request.args.get('jenis', '').strip()
    if jenis:
        query = query.filter_by(jenis=jenis)

    tgl_mulai = request.args.get('tgl_mulai', '').strip()
    if tgl_mulai:
        try:
            d_mulai = datetime.strptime(tgl_mulai, '%Y-%m-%d').date()
            query = query.filter(TransaksiKas.tanggal >= d_mulai)
        except ValueError:
            pass

    tgl_selesai = request.args.get('tgl_selesai', '').strip()
    if tgl_selesai:
        try:
            d_selesai = datetime.strptime(tgl_selesai, '%Y-%m-%d').date()
            query = query.filter(TransaksiKas.tanggal <= d_selesai)
        except ValueError:
            pass

    transaksi_list = query.order_by(TransaksiKas.tanggal.desc(), TransaksiKas.id.desc()).all()

    pemasukan = db.session.query(db.func.sum(TransaksiKas.jumlah)).filter_by(jenis='Pemasukan').scalar() or 0.0
    pengeluaran = db.session.query(db.func.sum(TransaksiKas.jumlah)).filter_by(jenis='Pengeluaran').scalar() or 0.0
    total_kas = pemasukan - pengeluaran

    return render_template(
        'kas/index.html',
        active_page='kas',
        transaksi_list=transaksi_list,
        total_pemasukan=pemasukan,
        total_pengeluaran=pengeluaran,
        total_kas=total_kas
    )

@app.route('/kas/tambah', methods=['GET', 'POST'])
@login_required
@admin_required
def kas_tambah():
    jenis = request.args.get('jenis', 'Pemasukan')
    if request.method == 'POST':
        jenis = request.form.get('jenis', 'Pemasukan')
        kategori = request.form.get('kategori', 'Lain-lain')
        judul = request.form.get('judul', '').strip()
        jumlah = float(request.form.get('jumlah', 0))
        keterangan = request.form.get('keterangan', '')
        
        tgl = date.today()
        tgl_str = request.form.get('tanggal')
        if tgl_str:
            try:
                tgl = datetime.strptime(tgl_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        user = get_current_user()
        kode = f"TRX-{datetime.now().strftime('%Y%m%d')}-{int(datetime.utcnow().timestamp()) % 10000}"

        trx = TransaksiKas(
            kode_transaksi=kode,
            jenis=jenis,
            kategori=kategori,
            judul=judul,
            jumlah=jumlah,
            tanggal=tgl,
            keterangan=keterangan,
            created_by=user.nama
        )
        db.session.add(trx)
        db.session.commit()
        flash(f'Transaksi kas {jenis} berhasil dicatat.', 'success')
        return redirect(url_for('kas_index'))

    return render_template('kas/form.html', active_page='kas', jenis=jenis, today_str=date.today().strftime('%Y-%m-%d'))

@app.route('/kas/hapus/<int:id>', methods=['POST'])
@login_required
@admin_required
def kas_hapus(id):
    trx = TransaksiKas.query.get_or_404(id)
    db.session.delete(trx)
    db.session.commit()
    flash('Transaksi kas telah dihapus.', 'info')
    return redirect(url_for('kas_index'))

@app.route('/kas/laporan')
@login_required
def kas_laporan():
    bulan = request.args.get('bulan', type=int)
    tahun = request.args.get('tahun', type=int)
    jenis = request.args.get('jenis', '').strip()

    query = TransaksiKas.query
    if jenis in ['Pemasukan', 'Pengeluaran']:
        query = query.filter_by(jenis=jenis)
    if tahun:
        query = query.filter(db.extract('year', TransaksiKas.tanggal) == tahun)
    if bulan:
        query = query.filter(db.extract('month', TransaksiKas.tanggal) == bulan)

    transaksi_list = query.order_by(TransaksiKas.tanggal.asc(), TransaksiKas.id.asc()).all()

    # Hitung total untuk transaksi yang terfilter
    pemasukan = sum(t.jumlah for t in transaksi_list if t.jenis == 'Pemasukan')
    pengeluaran = sum(t.jumlah for t in transaksi_list if t.jenis == 'Pengeluaran')
    total_kas = pemasukan - pengeluaran

    # Total kumulatif kas paguyuban menyeluruh
    total_kumulatif_pemasukan = db.session.query(db.func.sum(TransaksiKas.jumlah)).filter_by(jenis='Pemasukan').scalar() or 0.0
    total_kumulatif_pengeluaran = db.session.query(db.func.sum(TransaksiKas.jumlah)).filter_by(jenis='Pengeluaran').scalar() or 0.0
    saldo_kas_umum = total_kumulatif_pemasukan - total_kumulatif_pengeluaran

    settings = {s.kunci: s.nilai for s in Pengaturan.query.all()}
    nama_rt = settings.get('nama_rt', 'RT 09')
    nama_rw = settings.get('nama_rw', 'RW 14')
    kelurahan = settings.get('kelurahan', 'Mojosarirejo')
    kecamatan = settings.get('kecamatan', 'Driyorejo')
    kota = settings.get('kota', 'Gresik')
    provinsi = settings.get('provinsi', 'Jawa Timur')
    kode_pos = settings.get('kode_pos', '61177')
    nama_ketua = settings.get('nama_ketua_rt', 'H. Bambang Sutrisno')
    no_hp_rt = settings.get('no_hp_rt', '0812-3456-7890')

    bulan_names = {
        1: 'Januari', 2: 'Februari', 3: 'Maret', 4: 'April',
        5: 'Mei', 6: 'Juni', 7: 'Juli', 8: 'Agustus',
        9: 'September', 10: 'Oktober', 11: 'November', 12: 'Desember'
    }

    if bulan and tahun:
        periode_judul = f"Bulan {bulan_names.get(bulan, str(bulan))} {tahun}"
    elif tahun:
        periode_judul = f"Tahun Buku {tahun}"
    elif bulan:
        periode_judul = f"Bulan {bulan_names.get(bulan, str(bulan))} (Semua Tahun)"
    else:
        periode_judul = "Semua Riwayat Transaksi (Buku Kas Lengkap)"

    today_formal = date.today().strftime('%d %B %Y')
    now_str = datetime.now().strftime('%d-%m-%Y %H:%M')

    return render_template(
        'kas/laporan.html',
        transaksi_list=transaksi_list,
        total_pemasukan=pemasukan,
        total_pengeluaran=pengeluaran,
        total_kas=total_kas,
        saldo_kas_umum=saldo_kas_umum,
        periode_judul=periode_judul,
        filter_bulan=bulan,
        filter_tahun=tahun,
        filter_jenis=jenis,
        nama_rt=nama_rt,
        nama_rw=nama_rw,
        kelurahan=kelurahan,
        kecamatan=kecamatan,
        kota=kota,
        provinsi=provinsi,
        kode_pos=kode_pos,
        nama_ketua=nama_ketua,
        no_hp_rt=no_hp_rt,
        today_formal=today_formal,
        now_str=now_str
    )


# -------------------------------------------------------------
# 5. PERSURATAN
# -------------------------------------------------------------
@app.route('/persuratan')
@login_required
def persuratan_index():
    user = get_current_user()
    query = Surat.query.join(Warga)

    if user.role == 'warga' and user.warga_id:
        query = query.filter(Surat.warga_id == user.warga_id)

    status = request.args.get('status', '').strip()
    if status:
        query = query.filter(Surat.status == status)

    jenis = request.args.get('jenis', '').strip()
    if jenis:
        query = query.filter(Surat.jenis_surat == jenis)

    surat_list = query.order_by(Surat.tanggal_pengajuan.desc()).all()

    base_q = Surat.query
    if user.role == 'warga' and user.warga_id:
        base_q = base_q.filter_by(warga_id=user.warga_id)

    total_surat = base_q.count()
    diajukan_count = base_q.filter_by(status='Diajukan').count()
    diproses_count = base_q.filter_by(status='Diproses').count()
    disetujui_count = base_q.filter_by(status='Disetujui').count()

    return render_template(
        'persuratan/index.html',
        active_page='persuratan',
        surat_list=surat_list,
        total_surat=total_surat,
        diajukan_count=diajukan_count,
        diproses_count=diproses_count,
        disetujui_count=disetujui_count
    )

@app.route('/persuratan/ajukan', methods=['GET', 'POST'])
@login_required
def persuratan_ajukan():
    user = get_current_user()
    if request.method == 'POST':
        warga_id = request.form.get('warga_id')
        if user.role == 'warga' and user.warga_id:
            warga_id = user.warga_id
        
        jenis_surat = request.form.get('jenis_surat', 'Surat Pengantar RT (KTP/KK)')
        keperluan = request.form.get('keperluan', '').strip()

        # Capture extra template fields
        extra_data = {}
        for k in request.form:
            if k.startswith('extra_') and request.form[k]:
                extra_data[k] = request.form[k].strip()

        # Generate automatic formal letter number
        next_num = Surat.query.count() + 1
        romawi = {1: 'I', 2: 'II', 3: 'III', 4: 'IV', 5: 'V', 6: 'VI', 7: 'VII', 8: 'VIII', 9: 'IX', 10: 'X', 11: 'XI', 12: 'XII'}
        bln_romawi = romawi.get(datetime.now().month, 'IV')
        nomor_surat = f"{next_num:03d}/RT-09/RW-14/{bln_romawi}/{datetime.now().year}"

        s = Surat(
            nomor_surat=nomor_surat,
            warga_id=int(warga_id),
            jenis_surat=jenis_surat,
            keperluan=keperluan,
            data_tambahan=json.dumps(extra_data) if extra_data else None,
            status='Diajukan',
            tanggal_pengajuan=datetime.utcnow()
        )
        db.session.add(s)
        db.session.commit()
        flash(f'Pengajuan {jenis_surat} berhasil dikirim dengan Nomor Antrian {nomor_surat}.', 'success')
        return redirect(url_for('persuratan_index'))

    warga_all = Warga.query.filter_by(is_aktif=True).order_by(Warga.nama.asc()).all()
    return render_template('persuratan/ajukan.html', active_page='persuratan', warga_all=warga_all)

@app.route('/persuratan/<int:id>')
@login_required
def persuratan_detail(id):
    user = get_current_user()
    surat = Surat.query.get_or_404(id)

    # Restrict warga to own letters
    if user.role == 'warga' and user.warga_id and surat.warga_id != user.warga_id:
        flash('Akses ditolak. Anda hanya berhak melihat dokumen pengajuan surat Anda sendiri.', 'danger')
        return redirect(url_for('persuratan_index'))

    extra_data = {}
    if surat.data_tambahan:
        try:
            extra_data = json.loads(surat.data_tambahan)
        except Exception:
            pass

    return render_template(
        'persuratan/detail.html',
        active_page='persuratan',
        surat=surat,
        extra_data=extra_data
    )

@app.route('/persuratan/proses/<int:id>', methods=['POST'])
@login_required
@admin_required
def persuratan_proses(id):
    surat = Surat.query.get_or_404(id)
    user = get_current_user()

    status = request.form.get('status', 'Disetujui')
    catatan = request.form.get('catatan_petugas', '')

    surat.status = status
    surat.catatan_petugas = catatan
    if status == 'Disetujui':
        surat.tanggal_disetujui = datetime.utcnow()
        surat.approved_by = user.nama

    db.session.commit()
    flash(f'Status persuratan telah diperbarui menjadi "{status}".', 'success')
    return redirect(url_for('persuratan_detail', id=surat.id))

@app.route('/persuratan/cetak/<int:id>')
@login_required
def persuratan_cetak(id):
    user = get_current_user()
    surat = Surat.query.get_or_404(id)

    # Restrict warga to own letters
    if user.role == 'warga' and user.warga_id and surat.warga_id != user.warga_id:
        flash('Akses ditolak. Anda hanya berhak mencetak dokumen surat Anda sendiri.', 'danger')
        return redirect(url_for('persuratan_index'))

    extra_data = {}
    if surat.data_tambahan:
        try:
            extra_data = json.loads(surat.data_tambahan)
        except Exception:
            pass

    settings = {s.kunci: s.nilai for s in Pengaturan.query.all()}
    nama_rt = settings.get('nama_rt', 'RT 09')
    nama_rw = settings.get('nama_rw', 'RW 14')
    kelurahan = settings.get('kelurahan', 'Mojosarirejo')
    kecamatan = settings.get('kecamatan', 'Driyorejo')
    kota = settings.get('kota', 'Gresik')
    provinsi = settings.get('provinsi', 'Jawa Timur')
    kode_pos = settings.get('kode_pos', '601')
    nama_ketua = settings.get('nama_ketua_rt', 'H. Bambang Sutrisno')
    no_hp_rt = settings.get('no_hp_rt', '0812-3456-7890')

    today_formal = date.today().strftime('%d %B %Y')
    return render_template(
        'persuratan/print_template.html',
        surat=surat,
        extra_data=extra_data,
        today_formal=today_formal,
        nama_rt=nama_rt,
        nama_rw=nama_rw,
        kelurahan=kelurahan,
        kecamatan=kecamatan,
        kota=kota,
        provinsi=provinsi,
        kode_pos=kode_pos,
        nama_ketua=nama_ketua,
        no_hp_rt=no_hp_rt
    )


# -------------------------------------------------------------
# 6. PENGUMUMAN
# -------------------------------------------------------------
@app.route('/pengumuman')
@login_required
def pengumuman_index():
    pengumuman_list = Pengumuman.query.filter_by(is_aktif=True).order_by(Pengumuman.prioritas.desc(), Pengumuman.tanggal.desc(), Pengumuman.id.desc()).all()
    return render_template('pengumuman/index.html', active_page='pengumuman', pengumuman_list=pengumuman_list)

@app.route('/pengumuman/cetak/<int:id>')
@login_required
def pengumuman_cetak(id):
    p = Pengumuman.query.get_or_404(id)
    settings = {s.kunci: s.nilai for s in Pengaturan.query.all()}
    nama_rt = settings.get('nama_rt', 'RT 09')
    nama_rw = settings.get('nama_rw', 'RW 14')
    kelurahan = settings.get('kelurahan', 'Mojosarirejo')
    kecamatan = settings.get('kecamatan', 'Driyorejo')
    kota = settings.get('kota', 'Gresik')
    provinsi = settings.get('provinsi', 'Jawa Timur')
    kode_pos = settings.get('kode_pos', '601')
    nama_ketua = settings.get('nama_ketua_rt', 'H. Bambang Sutrisno')
    no_hp_rt = settings.get('no_hp_rt', '0812-3456-7890')

    tahun = p.tanggal.strftime('%Y') if p.tanggal else str(date.today().year)
    no_edaran = f"EDR/{nama_rt.replace(' ', '')}/{nama_rw.replace(' ', '')}/{tahun}/{str(p.id).zfill(3)}"
    today_formal = date.today().strftime('%d %B %Y')

    return render_template(
        'pengumuman/cetak_edaran.html',
        item=p,
        no_edaran=no_edaran,
        nama_rt=nama_rt,
        nama_rw=nama_rw,
        kelurahan=kelurahan,
        kecamatan=kecamatan,
        kota=kota,
        provinsi=provinsi,
        kode_pos=kode_pos,
        nama_ketua=nama_ketua,
        no_hp_rt=no_hp_rt,
        today_formal=today_formal
    )

@app.route('/pengumuman/tambah', methods=['POST'])
@login_required
@admin_required
def pengumuman_tambah():
    judul = request.form.get('judul', '').strip()
    konten = request.form.get('konten', '').strip()
    kategori = request.form.get('kategori', 'Info Warga')
    prioritas = request.form.get('prioritas', 'Biasa')

    user = get_current_user()
    p = Pengumuman(
        judul=judul,
        konten=konten,
        kategori=kategori,
        prioritas=prioritas,
        tanggal=date.today(),
        author=f"Pengurus {Pengaturan.get('nama_rt', 'RT 09')} / {Pengaturan.get('nama_rw', 'RW 14')}"
    )
    db.session.add(p)
    db.session.commit()
    flash('Pengumuman baru telah dipublikasikan di portal.', 'success')
    return redirect(url_for('pengumuman_index'))

@app.route('/pengumuman/hapus/<int:id>', methods=['POST'])
@login_required
@admin_required
def pengumuman_hapus(id):
    p = Pengumuman.query.get_or_404(id)
    db.session.delete(p)
    db.session.commit()
    flash('Pengumuman telah dihapus.', 'info')
    return redirect(url_for('pengumuman_index'))


# -------------------------------------------------------------
# 7. INVENTARIS: PENGADAAN, PEMINJAMAN, DISPOSAL
# -------------------------------------------------------------
@app.route('/inventaris')
@login_required
def inventaris_index():
    user = get_current_user()
    inventaris_list = Inventaris.query.order_by(Inventaris.nama_barang.asc()).all()

    # If regular warga, show only OWN borrowings!
    if user.role == 'warga' and user.warga_id:
        peminjaman_list = PeminjamanInventaris.query.filter_by(warga_id=user.warga_id).order_by(PeminjamanInventaris.created_at.desc()).all()
    else:
        peminjaman_list = PeminjamanInventaris.query.order_by(PeminjamanInventaris.created_at.desc()).all()

    disposal_list = DisposalInventaris.query.order_by(DisposalInventaris.tgl_disposal.desc()).all()

    total_items = Inventaris.query.count()
    tersedia_count = Inventaris.query.filter_by(status='Tersedia').count()
    dipinjam_count = Inventaris.query.filter_by(status='Dipinjam').count()
    disposal_count = Inventaris.query.filter_by(status='Disposal').count()

    return render_template(
        'inventaris/index.html',
        active_page='inventaris',
        inventaris_list=inventaris_list,
        peminjaman_list=peminjaman_list,
        disposal_list=disposal_list,
        total_items=total_items,
        tersedia_count=tersedia_count,
        dipinjam_count=dipinjam_count,
        disposal_count=disposal_count
    )

@app.route('/inventaris/tambah', methods=['GET', 'POST'])
@login_required
@admin_required
def inventaris_tambah():
    if request.method == 'POST':
        nama = request.form.get('nama_barang', '').strip()
        kategori = request.form.get('kategori', 'Peralatan')
        jumlah = int(request.form.get('jumlah', 1))
        satuan = request.form.get('satuan', 'Unit')
        kondisi = request.form.get('kondisi', 'Baik')
        lokasi = request.form.get('lokasi', 'Gudang RT 09')
        nilai = float(request.form.get('nilai_perolehan', 0) or 0)
        catatan = request.form.get('catatan', '')

        tgl = date.today()
        tgl_str = request.form.get('tgl_pengadaan')
        if tgl_str:
            try:
                tgl = datetime.strptime(tgl_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        kode = f"INV-RT09-{Inventaris.query.count() + 1:03d}"

        inv = Inventaris(
            kode_barang=kode,
            nama_barang=nama,
            kategori=kategori,
            jumlah=jumlah,
            satuan=satuan,
            kondisi=kondisi,
            lokasi=lokasi,
            tgl_pengadaan=tgl,
            nilai_perolehan=nilai,
            status='Tersedia',
            catatan=catatan
        )
        db.session.add(inv)
        db.session.commit()
        flash(f'Pengadaan barang {nama} ({kode}) berhasil dicatat.', 'success')
        return redirect(url_for('inventaris_index'))

    return render_template('inventaris/form.html', active_page='inventaris', today_str=date.today().strftime('%Y-%m-%d'))

@app.route('/inventaris/pinjam', methods=['GET', 'POST'])
@login_required
def inventaris_pinjam():
    if request.method == 'POST':
        inv_id = int(request.form.get('inventaris_id'))
        inv = Inventaris.query.get_or_404(inv_id)
        nama = request.form.get('nama_peminjam', '').strip()
        no_hp = request.form.get('no_hp', '').strip()
        jml = int(request.form.get('jumlah_pinjam', 1))
        keperluan = request.form.get('keperluan', '')

        tgl_p = date.today()
        try:
            tgl_p = datetime.strptime(request.form.get('tgl_pinjam'), '%Y-%m-%d').date()
            tgl_k = datetime.strptime(request.form.get('tgl_kembali_rencana'), '%Y-%m-%d').date()
        except Exception:
            tgl_k = tgl_p

        user = get_current_user()
        warga_id = user.warga_id if user else None

        pinjam = PeminjamanInventaris(
            inventaris_id=inv.id,
            warga_id=warga_id,
            nama_peminjam=nama,
            no_hp=no_hp,
            jumlah_pinjam=jml,
            tgl_pinjam=tgl_p,
            tgl_kembali_rencana=tgl_k,
            keperluan=keperluan,
            status='Dipinjam'
        )
        inv.status = 'Dipinjam'
        db.session.add(pinjam)
        db.session.commit()
        flash(f'Peminjaman {inv.nama_barang} berhasil dicatat.', 'success')
        return redirect(url_for('inventaris_index'))

    barang_tersedia = Inventaris.query.filter_by(status='Tersedia').all()
    return render_template('inventaris/pinjam_form.html', active_page='inventaris', barang_tersedia=barang_tersedia, today_str=date.today().strftime('%Y-%m-%d'))

@app.route('/inventaris/kembali/<int:id>', methods=['POST'])
@login_required
@admin_required
def inventaris_kembali(id):
    p = PeminjamanInventaris.query.get_or_404(id)
    p.status = 'Selesai'
    p.tgl_kembali_aktual = date.today()
    
    # Check if there are other active loans for this item
    other_active = PeminjamanInventaris.query.filter_by(inventaris_id=p.inventaris_id, status='Dipinjam').filter(PeminjamanInventaris.id != p.id).first()
    if not other_active:
        p.barang.status = 'Tersedia'

    db.session.commit()
    flash(f'Pengembalian barang {p.barang.nama_barang} telah dikonfirmasi selesai.', 'success')
    return redirect(url_for('inventaris_index'))

@app.route('/inventaris/disposal/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def inventaris_disposal(id):
    barang = Inventaris.query.get_or_404(id)
    if request.method == 'POST':
        alasan = request.form.get('alasan', '').strip()
        metode = request.form.get('metode', 'Dibuang / Rusak Total')
        residu = float(request.form.get('nilai_residu', 0) or 0)
        
        tgl = date.today()
        tgl_str = request.form.get('tgl_disposal')
        if tgl_str:
            try:
                tgl = datetime.strptime(tgl_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        user = get_current_user()
        disp = DisposalInventaris(
            inventaris_id=barang.id,
            tgl_disposal=tgl,
            alasan=alasan,
            metode=metode,
            nilai_residu=residu,
            disetujui_oleh=user.nama
        )
        barang.status = 'Disposal'
        barang.kondisi = 'Rusak Berat'
        db.session.add(disp)

        # If sold/auctioned, optionally record cash income
        if residu > 0:
            trx = TransaksiKas(
                kode_transaksi=f"TRX-DISP-{barang.id}-{int(datetime.utcnow().timestamp()) % 10000}",
                jenis='Pemasukan',
                kategori='Penyewaan Inventaris',
                judul=f"Hasil Disposal/Penjualan {barang.nama_barang}",
                jumlah=residu,
                tanggal=tgl,
                keterangan=f"Penjualan aset disposal: {alasan}",
                created_by=user.nama
            )
            db.session.add(trx)

        db.session.commit()
        flash(f'Disposal aset {barang.nama_barang} berhasil dicatat.', 'info')
        return redirect(url_for('inventaris_index'))

    return render_template('inventaris/disposal_form.html', active_page='inventaris', barang=barang, today_str=date.today().strftime('%Y-%m-%d'))

@app.route('/inventaris/hapus/<int:id>', methods=['POST'])
@login_required
@admin_required
def inventaris_hapus(id):
    inv = Inventaris.query.get_or_404(id)
    db.session.delete(inv)
    db.session.commit()
    flash('Aset inventaris telah dihapus dari sistem.', 'info')
    return redirect(url_for('inventaris_index'))


# -------------------------------------------------------------
# 8. PELAPORAN / PENGADUAN WARGA
# -------------------------------------------------------------
@app.route('/pelaporan')
@login_required
def pelaporan_index():
    user = get_current_user()
    query = Laporan.query

    status = request.args.get('status', '').strip()
    if status:
        query = query.filter_by(status=status)

    kategori = request.args.get('kategori', '').strip()
    if kategori:
        query = query.filter_by(kategori=kategori)

    laporan_list = query.order_by(Laporan.created_at.desc()).all()

    total_laporan = Laporan.query.count()
    menunggu_count = Laporan.query.filter_by(status='Menunggu').count()
    diproses_count = Laporan.query.filter_by(status='Diproses').count()
    selesai_count = Laporan.query.filter_by(status='Selesai').count()

    return render_template(
        'pelaporan/index.html',
        active_page='pelaporan',
        laporan_list=laporan_list,
        total_laporan=total_laporan,
        menunggu_count=menunggu_count,
        diproses_count=diproses_count,
        selesai_count=selesai_count
    )

@app.route('/pelaporan/ajukan', methods=['GET', 'POST'])
@login_required
def pelaporan_ajukan():
    if request.method == 'POST':
        nama = request.form.get('nama_pelapor', '').strip()
        judul = request.form.get('judul', '').strip()
        kategori = request.form.get('kategori', 'Lingkungan')
        lokasi = request.form.get('lokasi', '').strip()
        deskripsi = request.form.get('deskripsi', '').strip()

        foto_filename = None
        if 'foto' in request.files:
            f = request.files['foto']
            if f and f.filename != '':
                ext = os.path.splitext(f.filename)[1]
                fname = f"laporan_{int(datetime.utcnow().timestamp())}{ext}"
                f.save(os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(fname)))
                foto_filename = fname

        user = get_current_user()
        w_id = user.warga_id if user else None

        lap = Laporan(
            warga_id=w_id,
            nama_pelapor=nama,
            judul=judul,
            kategori=kategori,
            lokasi=lokasi,
            deskripsi=deskripsi,
            foto=foto_filename,
            status='Menunggu'
        )
        db.session.add(lap)
        db.session.commit()
        flash('Laporan masalah lingkungan Anda telah terkirim dan akan segera ditinjau oleh pengurus RT.', 'success')
        return redirect(url_for('pelaporan_index'))

    return render_template('pelaporan/ajukan.html', active_page='pelaporan')

@app.route('/pelaporan/<int:id>')
@login_required
def pelaporan_detail(id):
    lap = Laporan.query.get_or_404(id)
    return render_template('pelaporan/detail.html', active_page='pelaporan', laporan=lap)

@app.route('/pelaporan/tanggapi/<int:id>', methods=['POST'])
@login_required
@admin_required
def pelaporan_tanggapi(id):
    lap = Laporan.query.get_or_404(id)
    lap.status = request.form.get('status', 'Diproses')
    lap.tanggapan_petugas = request.form.get('tanggapan_petugas', '')
    lap.tindak_lanjut = request.form.get('tindak_lanjut', '')
    lap.updated_at = datetime.utcnow()

    db.session.commit()
    flash('Tanggapan dan status penanganan laporan berhasil diperbarui.', 'success')
    return redirect(url_for('pelaporan_detail', id=lap.id))


# -------------------------------------------------------------
# 9. PENGATURAN SISTEM
# -------------------------------------------------------------
@app.route('/pengaturan')
@login_required
@admin_required
def pengaturan_index():
    settings_all = Pengaturan.query.all()
    settings = {s.kunci: s.nilai for s in settings_all}
    user_list = User.query.order_by(User.id.asc()).all()
    warga_list = Warga.query.filter_by(is_aktif=True).order_by(Warga.nama.asc()).all()
    iuran_unpaid = Iuran.query.filter_by(status='Belum Lunas').order_by(Iuran.id.desc()).limit(15).all()

    return render_template(
        'pengaturan/index.html',
        active_page='pengaturan',
        settings=settings,
        user_list=user_list,
        warga_list=warga_list,
        iuran_unpaid=iuran_unpaid
    )

@app.route('/pengaturan/identitas', methods=['POST'])
@login_required
@admin_required
def pengaturan_simpan_identitas():
    keys = ['nama_rt', 'nama_rw', 'kelurahan', 'kecamatan', 'kota', 'kode_pos', 'nama_ketua_rt', 'no_hp_rt', 'iuran_bulanan']
    for k in keys:
        if k in request.form:
            Pengaturan.set(k, request.form[k], kategori='identitas')
    flash('Identitas wilayah RT berhasil disimpan.', 'success')
    return redirect(url_for('pengaturan_index'))

@app.route('/pengaturan/notifikasi', methods=['POST'])
@login_required
@superadmin_required
def pengaturan_simpan_notifikasi():
    keys = ['wa_api_url', 'wa_api_token', 'template_tagihan', 'template_konfirmasi_lunas', 'template_surat_selesai', 'template_pelaporan_respon']
    for k in keys:
        if k in request.form:
            Pengaturan.set(k, request.form[k], kategori='notifikasi')
    flash('Konfigurasi API notifikasi dan template pesan berhasil disimpan.', 'success')
    return redirect(url_for('pengaturan_index'))

@app.route('/pengaturan/qris', methods=['POST'])
@login_required
@superadmin_required
def pengaturan_simpan_qris():
    keys = [
        'qris_merchant_name', 'qris_nmid', 'bank_nama', 'bank_rekening', 'bank_atas_nama', 
        'qris_instruksi', 'qris_payload', 'mayar_is_active', 'mayar_environment', 'mayar_api_key', 'mayar_webhook_token'
    ]
    for k in keys:
        if k in request.form:
            Pengaturan.set(k, request.form[k].strip(), kategori='qris')
    flash('Pengaturan QRIS dan rekening kas berhasil diperbarui.', 'success')
    return redirect(url_for('pengaturan_index') + '?tab=qris')

@app.route('/pengaturan/mayar', methods=['POST'])
@login_required
@superadmin_required
def pengaturan_simpan_mayar():
    keys = ['mayar_is_active', 'mayar_environment', 'mayar_api_key', 'mayar_webhook_token']
    for k in keys:
        if k in request.form:
            Pengaturan.set(k, request.form[k].strip(), kategori='qris')
    flash('Konfigurasi Payment Gateway Mayar.id & Webhook QRIS berhasil disimpan.', 'success')
    return redirect(url_for('pengaturan_index') + '?tab=qris')

@app.route('/pengaturan/mayar/test-webhook', methods=['POST'])
@login_required
@superadmin_required
def pengaturan_mayar_test_webhook():
    """
    Simulasi pengujian Webhook Mayar langsung dari Dashboard Pengaturan.
    Mengirimkan event 'payment.received' ke endpoint /api/webhook/mayar
    untuk menguji verifikasi otomatis dan pencatatan Transaksi Kas.
    """
    iuran_id = request.form.get('iuran_id')
    if iuran_id and iuran_id.isdigit():
        iur = db.session.get(Iuran, int(iuran_id))
    else:
        iur = Iuran.query.filter_by(status='Belum Lunas').first()

    if not iur:
        flash('Tidak ditemukan tagihan iuran yang berstatus Belum Lunas untuk diuji.', 'warning')
        return redirect(url_for('pengaturan_index') + '?tab=qris')

    now_ts = int(datetime.utcnow().timestamp())
    dummy_payload = {
        "event": "payment.received",
        "data": {
            "id": f"tr_mayar_sim_{now_ts}",
            "status": True,
            "createdAt": datetime.utcnow().isoformat() + "Z",
            "updatedAt": datetime.utcnow().isoformat() + "Z",
            "merchantId": "mer_portalrt09",
            "merchantName": Pengaturan.get('qris_merchant_name', 'KAS PAGUYUBAN RT 09'),
            "customerName": iur.warga.nama,
            "customerMobile": iur.warga.no_hp or "081234567890",
            "customerEmail": iur.warga.email or "warga@portalrt.id",
            "amount": int(iur.jumlah),
            "paymentMethod": "QRIS",
            "paymentChannel": "MAYAR-QRIS",
            "invoiceId": f"inv_sim_{now_ts}",
            "description": f"Iuran Paguyuban RT 09 Periode {iur.periode_bulan}/{iur.periode_tahun} - {iur.warga.nama} [ID: #{iur.id}]"
        }
    }

    secret_token = Pengaturan.get('mayar_webhook_token', '').strip()
    with app.test_client() as client:
        res = client.post(f"/api/webhook/mayar?token={secret_token}", json=dummy_payload)
        if res.status_code == 200:
            res_data = res.get_json() or {}
            flash(f"✅ Simulasi Webhook Berhasil! {res_data.get('message', 'Pembayaran terverifikasi LUNAS.')}", 'success')
        else:
            flash(f"❌ Simulasi Webhook Gagal ({res.status_code}): {res.data.decode('utf-8')}", 'danger')

    return redirect(url_for('pengaturan_index') + '?tab=qris')

@app.route('/api/webhook/mayar', methods=['GET', 'POST'])
def api_webhook_mayar():
    """
    Endpoint resmi Webhook Mayar.id untuk verifikasi QRIS dan multi-channel payment otomatis.
    Menerima callback event 'payment.received' dari server Mayar.id.
    """
    if request.method == 'GET':
        return jsonify({
            'status': 'ok',
            'service': 'PortalRT Mayar Webhook Receiver',
            'timestamp': datetime.utcnow().isoformat(),
            'message': 'Endpoint webhook Mayar aktif. Gunakan method POST dengan JSON payload dan token otentikasi.'
        }), 200

    # 1. Otentikasi Webhook Token
    incoming_token = request.args.get('token')
    if not incoming_token:
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            incoming_token = auth_header.split('Bearer ', 1)[1].strip()
        elif auth_header:
            incoming_token = auth_header.strip()
    if not incoming_token:
        incoming_token = request.headers.get('X-Mayar-Token') or request.headers.get('X-Webhook-Secret')

    configured_token = Pengaturan.get('mayar_webhook_token', '').strip()
    if configured_token:
        if not incoming_token or incoming_token.strip() != configured_token:
            return jsonify({
                'status': 'error',
                'message': 'Unauthorized: Token autentikasi webhook Mayar tidak valid.'
            }), 401

    # 2. Parse JSON Payload
    payload = request.get_json(silent=True)
    if not payload:
        payload = request.form.to_dict() if request.form else {}

    event = str(payload.get('event') or payload.get('event.received') or '').lower()
    data = payload.get('data', {}) if isinstance(payload.get('data'), dict) else {}

    # Handle pengujian koneksi "TEST URL" / Ping dari dashboard Mayar
    if event in ['test', 'ping', 'webhook.test', 'test_url'] or not payload or (not data and not event):
        return jsonify({
            'status': 'ok',
            'message': 'Koneksi Webhook Mayar berhasil terhubung (TEST URL OK).',
            'service': 'PortalRT Mayar Webhook Receiver'
        }), 200

    # Event pembayaran berhasil di Mayar:
    # Di dashboard Mayar diberi label "Purchase", secara teknis dikirim sebagai "payment.received" atau "purchase"
    is_payment_success = (
        event in ['payment.received', 'purchase', 'payment.success', 'transaction.success', 'payment'] or
        data.get('status') in [True, 'SUCCESS', 'success', 'PAID', 'paid'] or
        payload.get('status') in [True, 'SUCCESS', 'success', 'PAID', 'paid']
    )

    if not is_payment_success:
        return jsonify({
            'status': 'ignored',
            'message': f"Event '{event}' atau status tidak memerlukan tindakan pelunasan iuran.",
            'event': event
        }), 200

    # 3. Ekstraksi Informasi Pembayaran
    transaction_id = str(data.get('id') or data.get('transactionId') or payload.get('id') or '').strip()
    invoice_id = str(data.get('invoiceId') or payload.get('invoiceId') or '').strip()
    payment_method = str(data.get('paymentMethod') or data.get('paymentChannel') or 'QRIS').upper()
    amount_paid = data.get('amount') or payload.get('amount')
    description = str(data.get('description') or payload.get('description') or '')
    customer_name = str(data.get('customerName') or payload.get('customerName') or '')
    customer_mobile = str(data.get('customerMobile') or payload.get('customerMobile') or '')

    # 4. Pencarian Iuran Terkait (Smart Matching)
    iuran_targets = []

    # Match 1: Invoice ID (mendukung single atau batch multi-bulan)
    if invoice_id:
        iuran_targets = Iuran.query.filter_by(mayar_invoice_id=invoice_id).all()

    # Match 2: Transaction ID
    if not iuran_targets and transaction_id:
        iuran_targets = Iuran.query.filter_by(mayar_transaction_id=transaction_id).all()

    # Match 3: Tag ID di description (e.g. "[Batch: 1,2,3]" atau "[ID: #123]" atau "#123")
    if not iuran_targets and description:
        batch_match = re.search(r'\[Batch:\s*([\d, ]+)\]', description)
        if batch_match:
            try:
                b_ids = [int(x.strip()) for x in batch_match.group(1).split(',') if x.strip().isdigit()]
                iuran_targets = Iuran.query.filter(Iuran.id.in_(b_ids)).all()
            except Exception:
                pass

        if not iuran_targets:
            match = re.search(r'#(\d+)', description)
            if match:
                try:
                    candidate_id = int(match.group(1))
                    candidate_iur = db.session.get(Iuran, candidate_id)
                    if candidate_iur:
                        iuran_targets = [candidate_iur]
                except Exception:
                    pass

    # Match 4: Nomor HP Warga (cari tagihan belum lunas)
    if not iuran_targets and customer_mobile:
        clean_mobile = ''.join(filter(str.isdigit, customer_mobile))
        if clean_mobile.startswith('62'):
            clean_mobile = '0' + clean_mobile[2:]
        if len(clean_mobile) >= 8:
            warga = Warga.query.filter(Warga.no_hp.like(f"%{clean_mobile[-8:]}%")).first()
            if warga:
                candidate_iur = Iuran.query.filter_by(warga_id=warga.id, status='Belum Lunas').order_by(
                    Iuran.periode_tahun.asc(), Iuran.periode_bulan.asc()
                ).first()
                if candidate_iur:
                    iuran_targets = [candidate_iur]

    # 5. Eksekusi Pelunasan
    if iuran_targets:
        first_iur = iuran_targets[0]
        all_lunas = all(x.status == 'Lunas' for x in iuran_targets)
        if all_lunas:
            return jsonify({
                'status': 'success',
                'message': f'Iuran ID #{first_iur.id} warga {first_iur.warga.nama} sudah lunas sebelumnya.',
                'iuran_id': first_iur.id,
                'already_settled': True
            }), 200

        now = datetime.utcnow()
        for target in iuran_targets:
            target.status = 'Lunas'
            target.metode_bayar = f"QRIS (Mayar - {payment_method})"
            target.tanggal_bayar = now
            target.verified_by = 'Sistem Webhook Mayar'
            target.verified_at = now
            if transaction_id:
                target.mayar_transaction_id = transaction_id
            if invoice_id:
                target.mayar_invoice_id = invoice_id
            target.catatan = f"Otomatis diverifikasi webhook Mayar.id | Trx: {transaction_id or '-'} | Inv: {invoice_id or '-'}"

        # Otomatis catat ke Transaksi Kas RT jika belum ada
        existing_trx = None
        for target in iuran_targets:
            existing_trx = TransaksiKas.query.filter_by(iuran_id=target.id).first()
            if existing_trx:
                break

        if not existing_trx:
            total_nominal = sum(x.jumlah for x in iuran_targets)
            nominal = float(amount_paid) if amount_paid else total_nominal
            if len(iuran_targets) > 1:
                periode_str = f"{len(iuran_targets)} Bulan ({first_iur.periode_bulan}/{first_iur.periode_tahun} s/d {iuran_targets[-1].periode_bulan}/{iuran_targets[-1].periode_tahun})"
            else:
                periode_str = f"Bulan {first_iur.periode_bulan}/{first_iur.periode_tahun}"

            trx = TransaksiKas(
                kode_transaksi=f"TRX-MAYAR-{first_iur.id}-{int(now.timestamp()) % 100000}",
                jenis='Pemasukan',
                kategori='Iuran Warga',
                judul=f"Iuran {periode_str} - {first_iur.warga.nama}",
                jumlah=nominal,
                tanggal=date.today(),
                keterangan=f"Pembayaran otomatis QRIS via Webhook Mayar ({payment_method}). ID Trx: {transaction_id or '-'}",
                iuran_id=first_iur.id,
                created_by='Sistem Webhook Mayar'
            )
            db.session.add(trx)

        db.session.commit()

        return jsonify({
            'status': 'success',
            'message': f'Iuran warga {first_iur.warga.nama} periode {first_iur.periode_bulan}/{first_iur.periode_tahun} berhasil diverifikasi Lunas via Mayar.',
            'iuran_id': first_iur.id,
            'count': len(iuran_targets),
            'warga': first_iur.warga.nama,
            'nominal': sum(x.jumlah for x in iuran_targets),
            'metode': first_iur.metode_bayar
        }), 200

    return jsonify({
        'status': 'not_matched',
        'message': 'Webhook valid diterima, namun tidak ada tagihan iuran yang cocok di database.',
        'transaction_id': transaction_id,
        'invoice_id': invoice_id
    }), 200

@app.route('/iuran/mayar/create/<int:id>', methods=['GET', 'POST'])
@login_required
def iuran_mayar_create(id):
    """
    Membuat tautan pembayaran online Mayar.id (Single Payment / QRIS Dinamis).
    Mengarahkan warga langsung ke halaman pembayaran Mayar.
    """
    iur = Iuran.query.get_or_404(id)
    user = get_current_user()

    # Hak Akses: Warga hanya boleh bayar iuran keluarganya
    if not user.is_admin():
        if not user.warga_id or user.warga_id != iur.warga_id:
            flash('Akses ditolak. Anda hanya berhak melakukan pembayaran iuran keluarga Anda.', 'danger')
            return redirect(url_for('iuran_index'))

    if iur.status == 'Lunas':
        flash('Tagihan iuran ini sudah berstatus LUNAS.', 'info')
        return redirect(url_for('iuran_index'))

    # Jika sudah punya payment link aktif sebelumnya, langsung arahkan
    if iur.mayar_payment_url:
        return redirect(iur.mayar_payment_url)

    api_key = Pengaturan.get('mayar_api_key', '').strip()
    env = Pengaturan.get('mayar_environment', 'sandbox').strip().lower()
    base_url = "https://api.mayar.id" if env == 'production' else "https://api.mayar.io"

    if not api_key:
        flash('Integrasi Mayar belum dikonfigurasi dengan API Key. Silakan lengkapi di menu Pengaturan QRIS & Mayar.', 'warning')
        return redirect(url_for('iuran_index'))

    endpoint = f"{base_url}/hl/v1/payment/create"
    redirect_url = request.host_url.rstrip('/') + url_for('iuran_index')
    payload_data = {
        "name": iur.warga.nama,
        "email": iur.warga.email or f"warga{iur.warga_id}@portalrt.id",
        "mobile": iur.warga.no_hp or "081234567890",
        "amount": int(iur.jumlah),
        "description": f"Iuran Paguyuban RT 09 Periode {iur.periode_bulan}/{iur.periode_tahun} - {iur.warga.nama} [ID: #{iur.id}]",
        "redirectUrl": redirect_url
    }

    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload_data).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'PortalRT-Mayar-Client/1.0'
        },
        method='POST'
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            res_body = json.loads(response.read().decode('utf-8'))
            data = res_body.get('data', {})
            inv_id = data.get('id') or data.get('transactionId')
            payment_link = data.get('link') or data.get('url')

            if payment_link:
                iur.mayar_invoice_id = str(inv_id)
                iur.mayar_payment_url = payment_link
                db.session.commit()
                return redirect(payment_link)
            else:
                flash('Respon Mayar tidak menyertakan link pembayaran. Silakan coba lagi.', 'danger')
                return redirect(url_for('iuran_index'))
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode('utf-8', errors='replace')
        flash(f'Gagal menghubungi API Mayar ({e.code}): {err_msg}', 'danger')
        return redirect(url_for('iuran_index'))
    except Exception as e:
        flash(f'Terjadi kendala koneksi ke server Mayar: {str(e)}', 'danger')
        return redirect(url_for('iuran_index'))

@app.route('/iuran/mayar/create-batch', methods=['POST'])
@login_required
def iuran_mayar_create_batch():
    """
    Membuat tautan pembayaran online Mayar.id untuk beberapa bulan iuran sekaligus.
    """
    user = get_current_user()
    raw_ids = request.form.getlist('iuran_ids')
    if not raw_ids and request.form.get('batch_iuran_ids'):
        raw_ids = [x.strip() for x in request.form.get('batch_iuran_ids').split(',') if x.strip()]

    try:
        iuran_ids = [int(x) for x in raw_ids if str(x).isdigit()]
    except Exception:
        iuran_ids = []

    if not iuran_ids:
        flash('Silakan pilih minimal satu tagihan iuran untuk pembayaran online.', 'warning')
        return redirect(url_for('iuran_index'))

    iurans = Iuran.query.filter(Iuran.id.in_(iuran_ids)).order_by(Iuran.periode_tahun.asc(), Iuran.periode_bulan.asc()).all()
    if not iurans:
        flash('Data tagihan yang dipilih tidak ditemukan.', 'danger')
        return redirect(url_for('iuran_index'))

    # Hak Akses
    if not user.is_admin():
        for iur in iurans:
            if not user.warga_id or user.warga_id != iur.warga_id:
                flash('Akses ditolak. Anda hanya berhak membayar tagihan iuran keluarga Anda.', 'danger')
                return redirect(url_for('iuran_index'))

    unpaid = [x for x in iurans if x.status != 'Lunas']
    if not unpaid:
        flash('Seluruh tagihan yang dipilih sudah berstatus LUNAS.', 'info')
        return redirect(url_for('iuran_index'))

    api_key = Pengaturan.get('mayar_api_key', '').strip()
    env = Pengaturan.get('mayar_environment', 'sandbox').strip().lower()
    base_url = "https://api.mayar.id" if env == 'production' else "https://api.mayar.io"

    if not api_key:
        flash('Integrasi Mayar belum dikonfigurasi dengan API Key. Silakan gunakan metode transfer atau hubungi pengurus.', 'warning')
        return redirect(url_for('iuran_index'))

    total_amount = int(sum(x.jumlah for x in unpaid))
    first_warga = unpaid[0].warga
    batch_ids_str = ",".join(str(x.id) for x in unpaid)
    batch_code = f"BATCH-{datetime.utcnow().strftime('%Y%m%d%H%M')}-{int(datetime.utcnow().timestamp()) % 10000}"

    if len(unpaid) > 1:
        periode_desc = f"{len(unpaid)} Bulan ({unpaid[0].periode_bulan}/{unpaid[0].periode_tahun} s/d {unpaid[-1].periode_bulan}/{unpaid[-1].periode_tahun})"
    else:
        periode_desc = f"Bulan {unpaid[0].periode_bulan}/{unpaid[0].periode_tahun}"

    endpoint = f"{base_url}/hl/v1/payment/create"
    redirect_url = request.host_url.rstrip('/') + url_for('iuran_index')
    payload_data = {
        "name": first_warga.nama,
        "email": first_warga.email or f"warga{first_warga.id}@portalrt.id",
        "mobile": first_warga.no_hp or "081234567890",
        "amount": total_amount,
        "description": f"Iuran Paguyuban RT 09 [{periode_desc}] - {first_warga.nama} [Batch: {batch_ids_str}]",
        "redirectUrl": redirect_url
    }

    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload_data).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'PortalRT-Mayar-Client/1.0'
        },
        method='POST'
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            res_body = json.loads(response.read().decode('utf-8'))
            data = res_body.get('data', {})
            inv_id = data.get('id') or data.get('transactionId')
            payment_link = data.get('link') or data.get('url')

            if payment_link:
                for iur in unpaid:
                    iur.kode_pembayaran = batch_code
                    iur.mayar_invoice_id = str(inv_id)
                    iur.mayar_payment_url = payment_link
                db.session.commit()
                return redirect(payment_link)
            else:
                flash('Respon Mayar tidak menyertakan link pembayaran. Silakan coba lagi.', 'danger')
                return redirect(url_for('iuran_index'))
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode('utf-8', errors='replace')
        flash(f'Gagal menghubungi API Mayar ({e.code}): {err_msg}', 'danger')
        return redirect(url_for('iuran_index'))
    except Exception as e:
        flash(f'Terjadi kendala koneksi ke server Mayar: {str(e)}', 'danger')
        return redirect(url_for('iuran_index'))

@app.route('/pengaturan/import/warga', methods=['POST'])
@login_required
@admin_required
def pengaturan_import_warga():
    if 'file_warga' not in request.files:
        flash('Silakan pilih berkas CSV untuk diunggah.', 'danger')
        return redirect(url_for('pengaturan_index'))

    file = request.files['file_warga']
    if not file or file.filename == '':
        flash('Berkas kosong.', 'danger')
        return redirect(url_for('pengaturan_index'))

    stream = io.StringIO(file.stream.read().decode('utf-8-sig', errors='replace'))
    csv_reader = csv.DictReader(stream)
    
    count = 0
    for row in csv_reader:
        nik = row.get('nik', '').strip().replace("'", "")
        if not nik:
            continue
        
        warga = Warga.query.filter_by(nik=nik).first()
        if not warga:
            tgl_l = None
            if row.get('tanggal_lahir'):
                try:
                    tgl_l = datetime.strptime(row['tanggal_lahir'].strip(), '%Y-%m-%d').date()
                except ValueError:
                    pass

            warga = Warga(
                nik=nik,
                no_kk=row.get('no_kk', '').strip().replace("'", ""),
                nama=row.get('nama', '').strip(),
                jenis_kelamin=row.get('jenis_kelamin', 'Laki-laki').strip(),
                tempat_lahir=row.get('tempat_lahir', '').strip(),
                tanggal_lahir=tgl_l,
                agama=row.get('agama', 'Islam').strip(),
                pekerjaan=row.get('pekerjaan', '').strip(),
                status_perkawinan=row.get('status_perkawinan', 'Kawin').strip(),
                status_keluarga=row.get('status_keluarga', 'Kepala Keluarga').strip(),
                status_tinggal=row.get('status_tinggal', 'Tetap').strip(),
                no_rumah=row.get('no_rumah', '').strip(),
                alamat=row.get('alamat', '').strip(),
                no_hp=row.get('no_hp', '').strip(),
                email=row.get('email', '').strip()
            )
            db.session.add(warga)
            count += 1

    db.session.commit()
    flash(f'Berhasil mengimpor {count} data warga baru dari berkas CSV.', 'success')
    return redirect(url_for('pengaturan_index'))

@app.route('/pengaturan/import/tagihan', methods=['POST'])
@login_required
@admin_required
def pengaturan_import_tagihan():
    if 'file_tagihan' not in request.files:
        flash('Silakan pilih berkas CSV tagihan.', 'danger')
        return redirect(url_for('pengaturan_index'))

    file = request.files['file_tagihan']
    if not file or file.filename == '':
        flash('Berkas kosong.', 'danger')
        return redirect(url_for('pengaturan_index'))

    stream = io.StringIO(file.stream.read().decode('utf-8-sig', errors='replace'))
    csv_reader = csv.DictReader(stream)
    
    count = 0
    for row in csv_reader:
        nik = row.get('nik', '').strip().replace("'", "")
        warga = Warga.query.filter_by(nik=nik).first()
        if warga:
            bln = int(row.get('periode_bulan', 5))
            thn = int(row.get('periode_tahun', 2026))
            jml = float(row.get('jumlah', 15000))
            st = row.get('status', 'Belum Lunas').strip()

            existing = Iuran.query.filter_by(warga_id=warga.id, periode_bulan=bln, periode_tahun=thn).first()
            if not existing:
                iur = Iuran(
                    warga_id=warga.id,
                    periode_bulan=bln,
                    periode_tahun=thn,
                    jumlah=jml,
                    status=st,
                    metode_bayar=row.get('metode_bayar', ''),
                    catatan=row.get('catatan', '')
                )
                db.session.add(iur)
                count += 1

    db.session.commit()
    flash(f'Berhasil mengimpor {count} data tagihan iuran baru.', 'success')
    return redirect(url_for('pengaturan_index'))

@app.route('/pengaturan/users/tambah', methods=['POST'])
@login_required
@superadmin_required
def pengaturan_tambah_user():
    username = request.form.get('username', '').strip()
    nama = request.form.get('nama', '').strip()
    pwd = request.form.get('password', '').strip()
    role = request.form.get('role', 'warga')
    user_type = request.form.get('user_type', 'warga_pemilik')
    warga_id_raw = request.form.get('warga_id')
    no_hp = request.form.get('no_hp', '').strip()

    if User.query.filter_by(username=username).first():
        flash(f'Username @{username} sudah digunakan.', 'danger')
        return redirect(url_for('pengaturan_index'))

    # Aturan penting: Superadmin BUKAN warga (warga_id=None)
    if role == 'superadmin' or user_type == 'superadmin':
        role = 'superadmin'
        user_type = 'superadmin'
        final_warga_id = None
    else:
        final_warga_id = int(warga_id_raw) if warga_id_raw and warga_id_raw.isdigit() else None
        if final_warga_id:
            w_obj = db.session.get(Warga, final_warga_id)
            if w_obj and request.form.get('user_type') not in ['warga_pemilik', 'warga_kontrak']:
                user_type = 'warga_kontrak' if w_obj.status_tinggal == 'Kontrak' else 'warga_pemilik'

    u = User(
        username=username,
        nama=nama,
        role=role,
        user_type=user_type,
        warga_id=final_warga_id,
        no_hp=no_hp,
        is_active=True
    )
    u.set_password(pwd)
    db.session.add(u)
    db.session.commit()
    flash(f'Akun @{username} berhasil dibuat (Tipe: {u.user_type_display}, Peran: {u.role_display}).', 'success')
    return redirect(url_for('pengaturan_index'))

@app.route('/pengaturan/users/edit/<int:id>', methods=['POST'])
@login_required
@superadmin_required
def pengaturan_edit_user(id):
    u = User.query.get_or_404(id)
    current_user = get_current_user()

    nama = request.form.get('nama', '').strip()
    role = request.form.get('role', 'warga').strip()
    warga_id_raw = request.form.get('warga_id')
    no_hp = request.form.get('no_hp', '').strip()
    is_active_val = request.form.get('is_active', '1')
    new_password = request.form.get('password', '').strip()

    # Cegah Superadmin mencabut peran superadmin dirinya sendiri atau menonaktifkan dirinya sendiri
    if current_user and current_user.id == u.id:
        if role != 'superadmin':
            flash('Anda tidak dapat mencabut peran Superadmin dari akun Anda sendiri saat sedang login.', 'danger')
            return redirect(url_for('pengaturan_index') + '?tab=users')
        if is_active_val != '1':
            flash('Anda tidak dapat menonaktifkan akun Superadmin Anda sendiri.', 'danger')
            return redirect(url_for('pengaturan_index') + '?tab=users')

    if nama:
        u.nama = nama
    u.no_hp = no_hp
    u.is_active = (is_active_val == '1')

    # Update Password jika diisi
    if new_password:
        if len(new_password) < 6:
            flash('Kata sandi baru minimal 6 karakter.', 'warning')
            return redirect(url_for('pengaturan_index') + '?tab=users')
        u.set_password(new_password)

    # Aturan Peran (Role) & Warga (Pergantian Pengurus / Hak Akses):
    if role == 'superadmin':
        u.role = 'superadmin'
        u.user_type = 'superadmin'
        u.warga_id = None
    else:
        # ketua_rt, pengurus, atau warga
        u.role = role
        final_warga_id = int(warga_id_raw) if warga_id_raw and warga_id_raw.isdigit() else None
        if final_warga_id is not None:
            u.warga_id = final_warga_id
            w_obj = db.session.get(Warga, final_warga_id)
            if w_obj:
                u.user_type = 'warga_kontrak' if w_obj.status_tinggal in ['Kontrak', 'Kost'] else 'warga_pemilik'
        elif u.warga_id:
            w_obj = db.session.get(Warga, u.warga_id)
            if w_obj:
                u.user_type = 'warga_kontrak' if w_obj.status_tinggal in ['Kontrak', 'Kost'] else 'warga_pemilik'
        else:
            u.user_type = 'warga_pemilik'

    db.session.commit()
    flash(f'Peran dan data akun @{u.username} berhasil diperbarui (Peran: {u.role_display}, Tipe: {u.user_type_display}).', 'success')
    return redirect(url_for('pengaturan_index') + '?tab=users')

@app.route('/pengaturan/users/reset/<int:id>', methods=['POST'])
@login_required
@superadmin_required
def pengaturan_reset_password(id):
    u = User.query.get_or_404(id)
    u.set_password('rt09pass')
    db.session.commit()
    flash(f'Password untuk akun @{u.username} berhasil direset menjadi "rt09pass".', 'info')
    return redirect(url_for('pengaturan_index') + '?tab=users')


# -------------------------------------------------------------
# APPLICATION ENTRYPOINT & DATABASE INITIALIZATION
# -------------------------------------------------------------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        seed_database()
    app.run(host='0.0.0.0', port=5000, debug=True)
