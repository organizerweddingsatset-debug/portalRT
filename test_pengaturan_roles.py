import unittest
from app import app, db
from models import User, Pengaturan

class TestPengaturanRoles(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()
        self.ctx = app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()

    def test_ketua_rt_pengaturan_view_and_permissions(self):
        """Ketua RT hanya boleh melihat dan mengakses Tab Identitas & Tab Import"""
        self.client.post('/login', data={'username': 'ketua_rt', 'password': 'pejabat123'}, follow_redirects=True)
        res = self.client.get('/pengaturan')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')

        # Tab yang HARUS ADA: Identitas RT & Import & Template
        self.assertIn('tabBtn-identitas', html)
        self.assertIn('Identitas RT', html)
        self.assertIn('tabBtn-import', html)
        self.assertIn('Import & Template', html)
        self.assertIn('tabContent-identitas', html)
        self.assertIn('tabContent-import', html)
        self.assertIn('Hak Akses: Identitas &amp; Import', html)

        # Tab yang TIDAK BOLEH ADA: Notifikasi, QRIS, Users, Modal Tambah User
        self.assertNotIn('tabBtn-notifikasi', html)
        self.assertNotIn('tabBtn-qris', html)
        self.assertNotIn('tabBtn-users', html)
        self.assertNotIn('tabContent-notifikasi', html)
        self.assertNotIn('tabContent-qris', html)
        self.assertNotIn('tabContent-users', html)
        self.assertNotIn('modalTambahUser', html)

        # Cek izin POST Identitas: DIPERBOLEHKAN
        post_identitas = self.client.post('/pengaturan/identitas', data={
            'nama_rt': 'RT 09',
            'nama_rw': 'RW 14',
            'nama_ketua_rt': 'H. Bambang Sutrisno'
        }, follow_redirects=True)
        self.assertEqual(post_identitas.status_code, 200)
        self.assertIn('Identitas wilayah RT berhasil disimpan.', post_identitas.data.decode('utf-8'))

        # Cek izin POST Notifikasi: DITOLAK (Superadmin only)
        post_notif = self.client.post('/pengaturan/notifikasi', data={
            'wa_api_url': 'https://hack.api'
        }, follow_redirects=True)
        self.assertIn('Akses ditolak. Fitur ini khusus untuk Superadmin sistem.', post_notif.data.decode('utf-8'))

        # Cek izin POST QRIS: DITOLAK (Superadmin only)
        post_qris = self.client.post('/pengaturan/qris', data={
            'qris_merchant_name': 'Hacked'
        }, follow_redirects=True)
        self.assertIn('Akses ditolak. Fitur ini khusus untuk Superadmin sistem.', post_qris.data.decode('utf-8'))

        # Cek izin POST Tambah User: DITOLAK (Superadmin only)
        post_user = self.client.post('/pengaturan/users/tambah', data={
            'username': 'fake_user',
            'nama': 'Fake User',
            'password': 'password123',
            'role': 'warga'
        }, follow_redirects=True)
        self.assertIn('Akses ditolak. Fitur ini khusus untuk Superadmin sistem.', post_user.data.decode('utf-8'))

        self.client.get('/logout', follow_redirects=True)
        print("[PASS] Ketua RT verified: Hanya tab Identitas & Import yang tampil dan dapat diakses")

    def test_pengurus_pengaturan_view_and_permissions(self):
        """Pengurus hanya boleh melihat dan mengakses Tab Identitas & Tab Import"""
        self.client.post('/login', data={'username': 'pengurus', 'password': 'pengurus123'}, follow_redirects=True)
        res = self.client.get('/pengaturan')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')

        # Tab yang HARUS ADA: Identitas RT & Import & Template
        self.assertIn('tabBtn-identitas', html)
        self.assertIn('tabBtn-import', html)
        self.assertIn('tabContent-identitas', html)
        self.assertIn('tabContent-import', html)
        self.assertIn('Hak Akses: Identitas &amp; Import', html)

        # Tab yang TIDAK BOLEH ADA: Notifikasi, QRIS, Users, Modal Tambah User
        self.assertNotIn('tabBtn-notifikasi', html)
        self.assertNotIn('tabBtn-qris', html)
        self.assertNotIn('tabBtn-users', html)
        self.assertNotIn('tabContent-notifikasi', html)
        self.assertNotIn('tabContent-qris', html)
        self.assertNotIn('tabContent-users', html)
        self.assertNotIn('modalTambahUser', html)

        # Cek izin POST QRIS: DITOLAK (Superadmin only)
        post_qris = self.client.post('/pengaturan/qris', data={
            'qris_merchant_name': 'Hacked'
        }, follow_redirects=True)
        self.assertIn('Akses ditolak. Fitur ini khusus untuk Superadmin sistem.', post_qris.data.decode('utf-8'))

        # Cek izin POST Reset Password User: DITOLAK (Superadmin only)
        post_reset = self.client.post('/pengaturan/users/reset/1', follow_redirects=True)
        self.assertIn('Akses ditolak. Fitur ini khusus untuk Superadmin sistem.', post_reset.data.decode('utf-8'))

        self.client.get('/logout', follow_redirects=True)
        print("[PASS] Pengurus verified: Hanya tab Identitas & Import yang tampil dan dapat diakses")

    def test_superadmin_pengaturan_full_view_and_permissions(self):
        """Superadmin dapat melihat dan mengelola seluruh 5 tab pengaturan"""
        self.client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)
        res = self.client.get('/pengaturan')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')

        # Seluruh 5 Tab harus ada
        self.assertIn('tabBtn-identitas', html)
        self.assertIn('tabBtn-notifikasi', html)
        self.assertIn('tabBtn-qris', html)
        self.assertIn('tabBtn-import', html)
        self.assertIn('tabBtn-users', html)
        self.assertIn('tabContent-identitas', html)
        self.assertIn('tabContent-notifikasi', html)
        self.assertIn('tabContent-qris', html)
        self.assertIn('tabContent-import', html)
        self.assertIn('tabContent-users', html)
        self.assertIn('modalTambahUser', html)
        self.assertIn('modalEditUser', html)
        self.assertIn('Edit Peran', html)
        self.assertIn('Hak Akses: Superadmin (Penuh)', html)

        self.client.get('/logout', follow_redirects=True)
        print("[PASS] Superadmin verified: Akses penuh ke seluruh tab pengaturan dan tombol Edit Peran")

    def test_edit_user_role_pergantian_pengurus(self):
        """Superadmin dapat mengatur peran (pergantian pengurus RT)"""
        # Pastikan username bersih sebelum tes
        existing = User.query.filter_by(username='calon_pengurus').first()
        if existing:
            db.session.delete(existing)
            db.session.commit()

        # Buat user sementara untuk pengujian pergantian pengurus
        test_user = User(
            username='calon_pengurus',
            nama='Budi Calon Pengurus',
            role='warga',
            user_type='warga_pemilik',
            is_active=True
        )
        test_user.set_password('warga123')
        db.session.add(test_user)
        db.session.commit()
        test_user_id = test_user.id

        # 1. Login sebagai Pengurus -> Coba edit peran (Harus DITOLAK)
        self.client.post('/login', data={'username': 'pengurus', 'password': 'pengurus123'}, follow_redirects=True)
        res_forbidden = self.client.post(f'/pengaturan/users/edit/{test_user_id}', data={
            'role': 'pengurus',
            'nama': 'Budi Calon Pengurus'
        }, follow_redirects=True)
        self.assertIn('Akses ditolak. Fitur ini khusus untuk Superadmin sistem.', res_forbidden.data.decode('utf-8'))
        self.client.get('/logout', follow_redirects=True)

        # 2. Login sebagai Superadmin -> Ubah peran warga menjadi Pengurus RT (Pergantian Pengurus)
        self.client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)
        res_promote = self.client.post(f'/pengaturan/users/edit/{test_user_id}', data={
            'role': 'pengurus',
            'nama': 'Budi Pengurus Baru, S.Kom',
            'no_hp': '081233445566',
            'is_active': '1'
        }, follow_redirects=True)
        self.assertEqual(res_promote.status_code, 200)
        self.assertIn('berhasil diperbarui', res_promote.data.decode('utf-8'))

        with app.app_context():
            updated_u = db.session.get(User, test_user_id)
            self.assertEqual(updated_u.role, 'pengurus')
            self.assertTrue(updated_u.is_pengurus())
            self.assertTrue(updated_u.is_admin())
            self.assertEqual(updated_u.nama, 'Budi Pengurus Baru, S.Kom')
            self.assertEqual(updated_u.no_hp, '081233445566')

        # 3. Ubah lagi peran menjadi Ketua RT
        res_ketua = self.client.post(f'/pengaturan/users/edit/{test_user_id}', data={
            'role': 'ketua_rt',
            'nama': 'Budi Pengurus Baru, S.Kom',
            'is_active': '1'
        }, follow_redirects=True)
        self.assertEqual(res_ketua.status_code, 200)

        with app.app_context():
            updated_u2 = db.session.get(User, test_user_id)
            self.assertEqual(updated_u2.role, 'ketua_rt')
            self.assertTrue(updated_u2.is_ketua_rt())

        # 4. Uji pencegahan Superadmin mencabut role sendiri
        admin_obj = User.query.filter_by(role='superadmin').first()
        res_self_demote = self.client.post(f'/pengaturan/users/edit/{admin_obj.id}', data={
            'role': 'warga',
            'nama': admin_obj.nama,
            'is_active': '1'
        }, follow_redirects=True)
        self.assertIn('Anda tidak dapat mencabut peran Superadmin dari akun Anda sendiri', res_self_demote.data.decode('utf-8'))

        # Cleanup test user
        with app.app_context():
            u_clean = db.session.get(User, test_user_id)
            if u_clean:
                db.session.delete(u_clean)
                db.session.commit()

        self.client.get('/logout', follow_redirects=True)
        print("[PASS] Pergantian pengurus verified: Superadmin sukses mengatur peran role pengguna")

    def test_warga_cannot_access_pengaturan(self):
        """Warga biasa tidak diizinkan membuka halaman pengaturan"""
        self.client.post('/login', data={'username': 'warga1', 'password': 'warga123'}, follow_redirects=True)
        res = self.client.get('/pengaturan', follow_redirects=True)
        html = res.data.decode('utf-8')
        self.assertIn('Akses ditolak', html)
        self.client.get('/logout', follow_redirects=True)
        print("[PASS] Warga access properly blocked from /pengaturan")

if __name__ == '__main__':
    unittest.main()
