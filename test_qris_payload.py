import unittest
import os
from app import app
from models import db, User, Pengaturan

class TestQrisPayloadFeature(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()

    def test_qrcode_js_asset_exists(self):
        """Pastikan script qrcode.min.js lokal tersedia dan valid"""
        js_path = os.path.join(self.app.root_path, 'static', 'js', 'qrcode.min.js')
        self.assertTrue(os.path.exists(js_path), "File static/js/qrcode.min.js harus ada")
        self.assertGreater(os.path.getsize(js_path), 5000, "Ukuran qrcode.min.js harus valid")

    def test_superadmin_view_qris_payload_input(self):
        """Superadmin dapat melihat input field QRIS payload dan live preview"""
        self.client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)
        res = self.client.get('/pengaturan?tab=qris')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')

        self.assertIn('name="qris_payload"', html)
        self.assertIn('id="input_qris_payload"', html)
        self.assertIn('QRIS Payload Data (EMVCo String Standard)', html)
        self.assertIn('qrisLivePreviewBox', html)
        self.assertIn('copyPayloadToClipboard', html)
        self.assertIn('qrcode.min.js', html)
        self.client.get('/logout', follow_redirects=True)
        print("[PASS] Superadmin verified: Field QRIS payload dan live preview aktif")

    def test_save_qris_payload(self):
        """Superadmin dapat menyimpan string payload QRIS EMVCo ke database"""
        self.client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)
        
        sample_payload = '00020101021126600016ID.CO.QRIS.WWW01189360052300000000010215ID10200300405060303UME51440014ID.CO.QRIS.WWW0215ID10200300405060303UME5204541153033605802ID5925KAS PAGUYUBAN RT 09 RW 146008DRIYOREJO61056117762200716KASRT09DRIYOREJO6304A1B2'
        
        res = self.client.post('/pengaturan/qris', data={
            'qris_merchant_name': 'KAS PAGUYUBAN RT 09 RW 14',
            'qris_nmid': 'ID1020030040506',
            'bank_nama': 'Bank Central Asia (BCA)',
            'bank_rekening': '8830-1928-31',
            'bank_atas_nama': 'PAGUYUBAN WARGA RT 09',
            'qris_instruksi': 'Scan QRIS untuk pembayaran kas',
            'qris_payload': sample_payload
        }, follow_redirects=True)

        self.assertEqual(res.status_code, 200)
        
        # Verifikasi nilai tersimpan di database
        with self.app.app_context():
            saved_payload = Pengaturan.get('qris_payload')
            self.assertEqual(saved_payload, sample_payload)

        self.client.get('/logout', follow_redirects=True)
        print("[PASS] Simpan QRIS payload ke database sukses")

    def test_iuran_page_qris_modal_has_payload_and_copy(self):
        """Halaman iuran menampilkan modal QRIS dinamis dengan fitur salin payload"""
        self.client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)
        res = self.client.get('/iuran')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')

        self.assertIn('qrisModal', html)
        self.assertIn('qrisModalBox', html)
        self.assertIn('copyQrisModalPayload', html)
        self.assertIn('Salin String QRIS (EMVCo Payload)', html)
        self.assertIn('qrcode.min.js', html)
        self.client.get('/logout', follow_redirects=True)
        print("[PASS] Modal QRIS warga dilengkapi rendering dynamic & copy payload")

if __name__ == '__main__':
    unittest.main()
