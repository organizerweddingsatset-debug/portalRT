import unittest
from app import app, db
from models import User

class TestDashboardRoles(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()

    def test_superadmin_dashboard(self):
        """Superadmin: Akun Pengguna, Unit Rumah, Audit Kas, Status Sistem"""
        self.client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        
        self.assertIn('Total Kas', html)
        self.assertIn('1.215.000', html)
        self.assertIn('Akun Pengguna', html)
        self.assertIn('Unit Rumah', html)
        self.assertIn('Status Sistem', html)
        self.assertIn('Aksi Cepat Super Administrator', html)
        self.assertIn('Master Rumah', html)
        self.assertIn('51 orang', html)
        self.client.get('/logout', follow_redirects=True)
        print("[PASS] Superadmin dashboard verified")

    def test_ketua_rt_dashboard(self):
        """Ketua RT: Kependudukan RT, Persetujuan Surat, Disposisi Surat, Aduan Warga"""
        self.client.post('/login', data={'username': 'ketua_rt', 'password': 'pejabat123'}, follow_redirects=True)
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        
        self.assertIn('Total Kas', html)
        self.assertIn('Kependudukan RT', html)
        self.assertIn('Persetujuan Surat', html)
        self.assertIn('Laporan Lingkungan', html)
        self.assertIn('Aksi Cepat Ketua RT', html)
        self.assertIn('Disposisi Surat', html)
        self.assertIn('Buat Pengumuman', html)
        self.client.get('/logout', follow_redirects=True)
        print("[PASS] Ketua RT dashboard verified")

    def test_pengurus_dashboard(self):
        """Pengurus: Verifikasi Iuran, Inventaris Dipinjam, Catat Arus Kas, Kelola Aset"""
        self.client.post('/login', data={'username': 'pengurus', 'password': 'pengurus123'}, follow_redirects=True)
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        
        self.assertIn('Total Kas', html)
        self.assertIn('Verifikasi Iuran', html)
        self.assertIn('Inventaris Dipinjam', html)
        self.assertIn('Permohonan Surat', html)
        self.assertIn('Aksi Cepat Pengurus Operasional', html)
        self.assertIn('Catat Arus Kas', html)
        self.assertIn('Kelola Aset', html)
        self.client.get('/logout', follow_redirects=True)
        print("[PASS] Pengurus dashboard verified")

    def test_warga_pemilik_dashboard(self):
        """Warga Pemilik: Status Iuran Rumah, Surat Pengantar Saya, Laporan Lingkungan Saya"""
        self.client.post('/login', data={'username': 'warga1', 'password': 'warga123'}, follow_redirects=True)
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        
        self.assertIn('Status Iuran Rumah', html)
        self.assertIn('Surat Pengantar Saya', html)
        self.assertIn('Laporan Lingkungan', html)
        self.assertIn('Transparansi dana RT', html)
        self.assertIn('Aksi Cepat Layanan Warga', html)
        self.assertIn('Bayar Iuran', html)
        self.assertIn('Ajukan Surat', html)
        self.client.get('/logout', follow_redirects=True)
        print("[PASS] Warga Pemilik dashboard verified")

    def test_warga_kontrak_dashboard(self):
        """Warga Kontrak: Ahmad Budiman Sujatmiko (AhmadG65)"""
        self.client.post('/login', data={'username': 'AhmadG65', 'password': 'warga123'}, follow_redirects=True)
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        
        self.assertIn('Ahmad Budiman Sujatmiko', html)
        self.assertIn('Warga Kontrak', html)
        self.assertIn('Status Iuran Rumah', html)
        self.assertIn('G/65', html)
        self.assertIn('Aksi Cepat Layanan Warga', html)
        self.client.get('/logout', follow_redirects=True)
        print("[PASS] Warga Kontrak (AhmadG65) dashboard verified")

if __name__ == '__main__':
    unittest.main()
