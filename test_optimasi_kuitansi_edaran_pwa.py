import unittest
import json
from app import app, terbilang_rupiah
from models import db, User, Warga, Iuran, Surat, Pengumuman, TransaksiKas, Pengaturan

class TestOptimasiKuitansiEdaranPWA(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def test_01_terbilang_rupiah_helper(self):
        """Uji konversi angka nominal ke huruf terbilang bahasa Indonesia"""
        self.assertEqual(terbilang_rupiah(0), "Nol Rupiah")
        self.assertEqual(terbilang_rupiah(15000), "Lima Belas Ribu Rupiah")
        self.assertEqual(terbilang_rupiah(50000), "Lima Puluh Ribu Rupiah")
        self.assertEqual(terbilang_rupiah(125000), "Seratus Dua Puluh Lima Ribu Rupiah")
        self.assertEqual(terbilang_rupiah(1500000), "Satu Juta Lima Ratus Ribu Rupiah")

    def test_02_kuitansi_iuran_route_and_template(self):
        """Uji cetak kuitansi resmi iuran dengan kop, nomor kuitansi, terbilang, dan QR verifikasi"""
        # Login sebagai admin
        with self.client:
            login_res = self.client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)
            self.assertEqual(login_res.status_code, 200)

            with self.app.app_context():
                iur = Iuran.query.first()
                self.assertIsNotNone(iur, "Harus ada data iuran di database")
                iur_id = iur.id

            kwt_res = self.client.get(f'/iuran/kuitansi/{iur_id}')
            self.assertEqual(kwt_res.status_code, 200)
            data_html = kwt_res.data.decode('utf-8')
            
            # Verifikasi elemen penting kuitansi
            self.assertIn("KUITANSI PEMBAYARAN IURAN", data_html)
            self.assertIn("KWT/", data_html)
            self.assertIn("Terbilang:", data_html)
            self.assertIn("Rupiah", data_html)
            self.assertIn("VERIFIKASI DIGITAL PORTAL RT", data_html)
            self.assertIn("Bendahara Paguyuban", data_html)

    def test_03_surat_resmi_kop_and_qr_verification(self):
        """Uji cetak surat resmi pengantar RT dengan kop dinamis dan QR keabsahan"""
        with self.client:
            self.client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)

            with self.app.app_context():
                surat = Surat.query.first()
                self.assertIsNotNone(surat, "Harus ada data surat di database")
                surat_id = surat.id

            res = self.client.get(f'/persuratan/cetak/{surat_id}')
            self.assertEqual(res.status_code, 200)
            html = res.data.decode('utf-8')

            self.assertIn("RUKUN TETANGGA", html)
            self.assertIn("VERIFIKASI SAH DIGITAL", html)
            self.assertIn("CAP & TTD DIGITAL RESMI", html)

    def test_04_surat_edaran_cetak_route(self):
        """Uji cetak Surat Edaran resmi RT dari pengumuman"""
        with self.client:
            self.client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)

            with self.app.app_context():
                pengumuman = Pengumuman.query.first()
                if not pengumuman:
                    pengumuman = Pengumuman(judul='Uji Edaran Gotong Royong', konten='Diharapkan hadir.', kategori='Info Warga')
                    db.session.add(pengumuman)
                    db.session.commit()
                p_id = pengumuman.id

            res = self.client.get(f'/pengumuman/cetak/{p_id}')
            self.assertEqual(res.status_code, 200)
            html = res.data.decode('utf-8')

            self.assertIn("SURAT EDARAN", html)
            self.assertIn("EDR/", html)
            self.assertIn("Kepada Yth:", html)
            self.assertIn("SURAT EDARAN RESMI", html)

    def test_05_laporan_kas_format_and_signatures(self):
        """Uji laporan kas keuangan dengan kop dinamis, tabel, dan tanda tangan ganda"""
        with self.client:
            self.client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)

            res = self.client.get('/kas/laporan')
            self.assertEqual(res.status_code, 200)
            html = res.data.decode('utf-8')

            self.assertIn("BUKU LAPORAN KAS & KEUANGAN", html)
            self.assertIn("AUDIT DIGITAL PORTAL", html)
            self.assertIn("TERVALIDASI SAH", html)
            self.assertIn("Bendahara Paguyuban", html)

    def test_06_pwa_manifest_and_sw_assets(self):
        """Uji file manifest.json dan sw.js untuk kualifikasi PWA"""
        manifest_res = self.client.get('/static/manifest.json')
        self.assertEqual(manifest_res.status_code, 200)
        manifest_data = json.loads(manifest_res.data.decode('utf-8'))
        self.assertIn("name", manifest_data)
        self.assertEqual(manifest_data["display"], "standalone")
        self.assertIn("icons", manifest_data)

        sw_res = self.client.get('/static/sw.js')
        self.assertEqual(sw_res.status_code, 200)
        self.assertIn(b"CACHE_NAME", sw_res.data)
        self.assertIn(b"addEventListener", sw_res.data)

if __name__ == '__main__':
    unittest.main()
