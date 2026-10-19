import unittest
import json
from datetime import datetime, date
from app import app, db
from models import User, Warga, Iuran, TransaksiKas, Pengaturan

class TestMayarWebhookIntegration(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.app = app
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.modified_iuran_ids = []

        # Konfigurasi pengaturan Mayar untuk testing
        Pengaturan.set('mayar_is_active', '1', kategori='qris')
        Pengaturan.set('mayar_environment', 'sandbox', kategori='qris')
        Pengaturan.set('mayar_webhook_token', 'test_secret_token_123', kategori='qris')
        Pengaturan.set('mayar_api_key', 'test_api_key_abc', kategori='qris')
        db.session.commit()

    def tearDown(self):
        # Bersihkan transaksi kas uji coba agar saldo awal kas tetap utuh (Rp 1.215.000)
        test_kas = TransaksiKas.query.filter(TransaksiKas.kode_transaksi.like('TRX-MAYAR-%')).all()
        for tk in test_kas:
            db.session.delete(tk)

        # Kembalikan status tagihan uji coba ke status semula
        for mid in self.modified_iuran_ids:
            iur = db.session.get(Iuran, mid)
            if iur:
                iur.status = 'Belum Lunas'
                iur.metode_bayar = 'Tunai / Cash'
                iur.mayar_invoice_id = None
                iur.mayar_transaction_id = None
                iur.mayar_payment_url = None
                iur.verified_by = None
                iur.verified_at = None
                iur.tanggal_bayar = None

        Pengaturan.set('mayar_api_key', '')
        Pengaturan.set('mayar_webhook_token', 'mayar_rt09_secret_token_2026')
        db.session.commit()
        self.ctx.pop()

    def test_get_webhook_endpoint(self):
        """GET request ke endpoint webhook mengembalikan status OK dan info service"""
        res = self.client.get('/api/webhook/mayar')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get('status'), 'ok')
        self.assertIn('Mayar', data.get('service'))
        print("[PASS] GET /api/webhook/mayar returns 200 OK service info")

    def test_webhook_unauthorized_token(self):
        """POST ke webhook tanpa token atau dengan token salah ditolak 401"""
        # Tanpa token
        res = self.client.post('/api/webhook/mayar', json={'event': 'payment.received'})
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertEqual(data.get('status'), 'error')

        # Token salah
        res_wrong = self.client.post('/api/webhook/mayar?token=salah_token', json={'event': 'payment.received'})
        self.assertEqual(res_wrong.status_code, 401)
        print("[PASS] Webhook security blocks unauthorized / missing token with 401")

    def test_webhook_payment_received_and_kas_creation(self):
        """Webhook payment.received berhasil melunasi iuran dan mencatat mutasi kas masuk"""
        # Cari tagihan iuran yang belum lunas
        iur = Iuran.query.filter_by(status='Belum Lunas').first()
        self.assertIsNotNone(iur, "Harus ada tagihan iuran Belum Lunas untuk diuji")

        iur_id = iur.id
        self.modified_iuran_ids.append(iur_id)
        iur_warga_nama = iur.warga.nama
        iur_nominal = iur.jumlah

        now_ts = int(datetime.utcnow().timestamp())
        trx_id = f"tr_test_mayar_{now_ts}"
        inv_id = f"inv_test_mayar_{now_ts}"

        # Simpan invoice ID ke iur untuk pengujian matching via invoice
        iur.mayar_invoice_id = inv_id
        db.session.commit()

        webhook_payload = {
            "event": "payment.received",
            "data": {
                "id": trx_id,
                "status": True,
                "createdAt": datetime.utcnow().isoformat() + "Z",
                "updatedAt": datetime.utcnow().isoformat() + "Z",
                "amount": int(iur_nominal),
                "paymentMethod": "QRIS",
                "paymentChannel": "SHOPEEPAY",
                "invoiceId": inv_id,
                "customerName": iur_warga_nama,
                "customerMobile": iur.warga.no_hp or "081234567890",
                "description": f"Iuran Paguyuban RT 09 [ID: #{iur_id}]"
            }
        }

        # Kirim webhook dengan token valid via query param
        res = self.client.post(
            f"/api/webhook/mayar?token=test_secret_token_123",
            json=webhook_payload
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data.get('status'), 'success')
        self.assertEqual(data.get('iuran_id'), iur_id)

        # Refresh database dan periksa status
        db.session.expire_all()
        updated_iur = db.session.get(Iuran, iur_id)
        self.assertEqual(updated_iur.status, 'Lunas')
        self.assertIn('Mayar', updated_iur.metode_bayar)
        self.assertEqual(updated_iur.mayar_transaction_id, trx_id)
        self.assertEqual(updated_iur.verified_by, 'Sistem Webhook Mayar')

        # Periksa pencatatan kas RT
        kas_trx = TransaksiKas.query.filter_by(iuran_id=iur_id).first()
        self.assertIsNotNone(kas_trx, "Transaksi Kas RT harus otomatis terbuat")
        self.assertEqual(kas_trx.jenis, 'Pemasukan')
        self.assertEqual(kas_trx.kategori, 'Iuran Warga')
        self.assertEqual(kas_trx.jumlah, iur_nominal)

        # Uji Idempotensi: Kirim ulang webhook yang sama, tidak boleh menduplikasi kas
        kas_count_before = TransaksiKas.query.filter_by(iuran_id=iur_id).count()
        res_dup = self.client.post(
            f"/api/webhook/mayar?token=test_secret_token_123",
            json=webhook_payload
        )
        self.assertEqual(res_dup.status_code, 200)
        kas_count_after = TransaksiKas.query.filter_by(iuran_id=iur_id).count()
        self.assertEqual(kas_count_before, kas_count_after, "Idempotensi: Transaksi Kas tidak boleh terduplikasi")
        print("[PASS] Webhook payment.received successfully settles iuran, logs kas, and is idempotent")

    def test_webhook_auth_via_header(self):
        """Webhook menerima otentikasi token via header HTTP (Authorization: Bearer atau X-Mayar-Token)"""
        iur = Iuran.query.filter_by(status='Belum Lunas').first()
        self.assertIsNotNone(iur)
        self.modified_iuran_ids.append(iur.id)

        now_ts = int(datetime.utcnow().timestamp())
        payload = {
            "event": "payment.received",
            "data": {
                "id": f"tr_header_{now_ts}",
                "status": True,
                "amount": int(iur.jumlah),
                "paymentMethod": "QRIS",
                "description": f"Iuran Paguyuban RT 09 [ID: #{iur.id}]"
            }
        }

        # Via Authorization: Bearer
        res_bearer = self.client.post(
            '/api/webhook/mayar',
            headers={'Authorization': 'Bearer test_secret_token_123'},
            json=payload
        )
        self.assertEqual(res_bearer.status_code, 200)
        print("[PASS] Webhook authentication via Authorization: Bearer token works")

    def test_pengaturan_mayar_roles_permission(self):
        """Hanya superadmin yang boleh menyimpan pengaturan Mayar dan menjalankan simulasi test"""
        # 1. Warga biasa mencoba POST /pengaturan/mayar: ditolak (302 redirect)
        self.client.post('/login', data={'username': 'warga1', 'password': 'warga123'})
        res_warga = self.client.post('/pengaturan/mayar', data={'mayar_is_active': '0'})
        self.assertEqual(res_warga.status_code, 302)

        # 2. Login sebagai superadmin
        self.client.get('/logout')
        res_login = self.client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)
        self.assertEqual(res_login.status_code, 200)

        # 3. Superadmin simpan konfigurasi
        res_admin = self.client.post('/pengaturan/mayar', data={
            'mayar_is_active': '1',
            'mayar_environment': 'sandbox',
            'mayar_api_key': 'superadmin_custom_key',
            'mayar_webhook_token': 'my_custom_secret'
        }, follow_redirects=True)
        self.assertEqual(res_admin.status_code, 200)

        db.session.expire_all()
        self.assertEqual(Pengaturan.get('mayar_api_key'), 'superadmin_custom_key')
        self.assertEqual(Pengaturan.get('mayar_webhook_token'), 'my_custom_secret')

        # 4. Test simulasi webhook endpoint dari dashboard
        target_iur = Iuran.query.filter_by(status='Belum Lunas').first()
        if target_iur:
            self.modified_iuran_ids.append(target_iur.id)
            res_sim = self.client.post('/pengaturan/mayar/test-webhook', data={'iuran_id': str(target_iur.id)}, follow_redirects=True)
        else:
            res_sim = self.client.post('/pengaturan/mayar/test-webhook', follow_redirects=True)
        self.assertEqual(res_sim.status_code, 200)
        self.assertIn('Simulasi Webhook', res_sim.data.decode('utf-8'))
        print("[PASS] Role-based access control and dashboard simulation test verified")

if __name__ == '__main__':
    unittest.main()
