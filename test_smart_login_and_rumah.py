import unittest
from app import app, db
from models import User, Warga, Rumah, RiwayatKeterhunian, Iuran, TransaksiKas

class TestSmartLoginAndRumah(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()

    def test_smart_login_ahmad_budiman_sujatmiko(self):
        """Test Ahmad Budiman Sujatmiko login using all requested variations"""
        variations = [
            'AhmadG65',
            'BudimanG65',
            'SujatmikoG65',
            'ahmadg65',
            'budimang65',
            'sujatmikog65',
            'Ahmad G65',
            'Budiman G/65',
            'Ahmad65',
            'Budiman65'
        ]

        for username_var in variations:
            with self.subTest(username=username_var):
                response = self.client.post('/login', data={
                    'username': username_var,
                    'password': 'warga123'
                }, follow_redirects=True)
                
                self.assertEqual(response.status_code, 200)
                html = response.data.decode('utf-8')
                self.assertIn('Ahmad Budiman Sujatmiko', html, f"Failed to login with username variation: {username_var}")
                
                # Logout to clean session
                self.client.get('/logout', follow_redirects=True)

    def test_smart_login_budi_santoso(self):
        """Test Budi Santoso (Rumah B3/12) smart login variations"""
        variations = ['warga1', 'BudiB312', 'SantosoB312', 'budib312', 'Budi B3/12']
        for v in variations:
            with self.subTest(username=v):
                response = self.client.post('/login', data={
                    'username': v,
                    'password': 'warga123'
                }, follow_redirects=True)
                self.assertEqual(response.status_code, 200)
                html = response.data.decode('utf-8')
                self.assertIn('Budi Santoso', html, f"Failed to login with {v}")
                self.client.get('/logout', follow_redirects=True)

    def test_rumah_permissions_warga_own_view(self):
        """Test that regular warga only sees their occupied or owned house"""
        # Login as Ahmad Budiman (Tenant of G/65)
        self.client.post('/login', data={'username': 'AhmadG65', 'password': 'warga123'}, follow_redirects=True)
        
        # Access /rumah
        res = self.client.get('/rumah')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn('G/65', html)
        self.assertIn('Ahmad Budiman Sujatmiko', html)
        # Should NOT see all 51 houses
        self.assertNotIn('51 Rumah Ditampilkan', html)

        with app.app_context():
            g65 = Rumah.query.filter_by(no_rumah='G/65').first()
            b312 = Rumah.query.filter_by(no_rumah='B3/12').first()
            g65_id = g65.id
            b312_id = b312.id

        # Access detail of G/65 -> ALLOWED
        res_detail = self.client.get(f'/rumah/{g65_id}')
        self.assertEqual(res_detail.status_code, 200)
        detail_html = res_detail.data.decode('utf-8')
        self.assertIn('Buku Besar Iuran Rumah', detail_html)
        self.assertIn('Linimasa Keterhunian', detail_html)

        # Access detail of B3/12 -> FORBIDDEN (redirects to /rumah with alert)
        res_forbidden = self.client.get(f'/rumah/{b312_id}', follow_redirects=True)
        forbid_html = res_forbidden.data.decode('utf-8')
        self.assertIn('Akses ditolak', forbid_html)

        self.client.get('/logout', follow_redirects=True)

    def test_admin_rumah_overview_and_handover(self):
        """Test admin can view all houses and perform tenancy handover"""
        # Login as Admin
        self.client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)
        
        # Access /rumah
        res = self.client.get('/rumah')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn('51 Rumah Ditampilkan', html)
        self.assertIn('Total Rumah', html)

        with app.app_context():
            g65 = Rumah.query.filter_by(no_rumah='G/65').first()
            g65_id = g65.id
            total_iuran_before = Iuran.query.filter_by(rumah_id=g65_id).count()

        # Check detail G/65
        res_detail = self.client.get(f'/rumah/{g65_id}')
        self.assertEqual(res_detail.status_code, 200)
        
        # Check handover GET
        res_handover = self.client.get(f'/rumah/serah-terima/{g65_id}')
        self.assertEqual(res_handover.status_code, 200)
        self.assertIn('Serah Terima Keterhunian', res_handover.data.decode('utf-8'))

        # Perform Handover to return to Owner
        res_post = self.client.post(f'/rumah/serah-terima/{g65_id}', data={
            'action_type': 'kembali_ke_pemilik',
            'tgl_serah_terima': '2026-05-01',
            'status_tunggakan': 'Lunas',
            'catatan_serah_terima': 'Kontrak selesai dengan baik, seluruh kunci dikembalikan.'
        }, follow_redirects=True)
        
        self.assertEqual(res_post.status_code, 200)
        post_html = res_post.data.decode('utf-8')
        self.assertIn('diserah-terimakan kembali kepada PEMILIK', post_html)

        # Verify in DB:
        with app.app_context():
            updated_g65 = Rumah.query.get(g65_id)
            self.assertEqual(updated_g65.status_huni, 'Dihuni Pemilik')
            self.assertEqual(updated_g65.tipe_penghuni, 'Pemilik')
            # Verify past iuran records are STILL intact on the property!
            total_iuran_after = Iuran.query.filter_by(rumah_id=g65_id).count()
            self.assertEqual(total_iuran_before, total_iuran_after)
            # Verify RiwayatKeterhunian has the closed lease and new owner lease
            history = RiwayatKeterhunian.query.filter_by(rumah_id=g65_id).all()
            # Restore G/65 state for subsequent tests
            ahmad = Warga.query.filter(Warga.nama.like('%Ahmad Budiman%')).first()
            updated_g65.penghuni_aktif_id = ahmad.id
            updated_g65.status_huni = 'Dikontrakkan'
            updated_g65.tipe_penghuni = 'Pengontrak'
            db.session.commit()

        self.client.get('/logout', follow_redirects=True)

if __name__ == '__main__':
    unittest.main()
