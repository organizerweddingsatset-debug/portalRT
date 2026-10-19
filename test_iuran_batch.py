import unittest
from datetime import datetime, date
from app import app, db
from models import User, Warga, Iuran, TransaksiKas

class TestIuranBatchPayment(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()
        self.ctx = app.app_context()
        self.ctx.push()

    def tearDown(self):
        db.session.rollback()
        self.ctx.pop()

    def test_admin_bayar_batch_lunas(self):
        """Admin mencatat pembayaran multi-bulan sekaligus (status langsung Lunas dan 1 kas gabungan)"""
        # Login admin
        self.client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)
        
        # Cari warga yang punya minimal 3 tagihan belum lunas
        warga = Warga.query.filter_by(is_aktif=True).first()
        unpaid_iurans = Iuran.query.filter_by(warga_id=warga.id, status='Belum Lunas').limit(3).all()
        if len(unpaid_iurans) < 3:
            for b in [10, 11, 12]:
                i = Iuran(warga_id=warga.id, periode_bulan=b, periode_tahun=2025, jumlah=15000.0, status='Belum Lunas')
                db.session.add(i)
            db.session.commit()
            unpaid_iurans = Iuran.query.filter_by(warga_id=warga.id, status='Belum Lunas').limit(3).all()

        ids = [i.id for i in unpaid_iurans]
        expected_total = sum(i.jumlah for i in unpaid_iurans)

        # Post batch payment
        res = self.client.post('/iuran/bayar-batch', data={
            'iuran_ids': ids,
            'metode_bayar': 'Tunai / Cash',
            'catatan': 'Pembayaran tunai 3 bulan sekaligus'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        # Verifikasi status di database
        updated = Iuran.query.filter(Iuran.id.in_(ids)).all()
        for u in updated:
            self.assertEqual(u.status, 'Lunas')
            self.assertIsNotNone(u.kode_pembayaran)
            self.assertTrue(u.kode_pembayaran.startswith('BATCH-'))
            self.assertEqual(u.metode_bayar, 'Tunai / Cash')

        # Pastikan kode_pembayaran sama untuk semua item dalam batch
        batch_codes = set(u.kode_pembayaran for u in updated)
        self.assertEqual(len(batch_codes), 1)

        # Pastikan tercatat 1 transaksi kas gabungan
        batch_code = list(batch_codes)[0]
        kas = TransaksiKas.query.filter_by(kode_transaksi=f"TRX-IUR-{batch_code}").first()
        self.assertIsNotNone(kas)
        self.assertEqual(kas.jumlah, expected_total)
        self.assertEqual(kas.jenis, 'Pemasukan')
        print(f"[PASS] Admin bayar batch {len(ids)} bulan berhasil: Total Rp {expected_total:,.0f}, Kas: {kas.kode_transaksi}")

        # Cleanup
        db.session.delete(kas)
        for u in updated:
            u.status = 'Belum Lunas'
            u.kode_pembayaran = None
        db.session.commit()
        self.client.get('/logout', follow_redirects=True)

    def test_warga_bayar_batch_menunggu_konfirmasi(self):
        """Warga mengirim bukti pembayaran beberapa bulan sekaligus (status Menunggu Konfirmasi)"""
        # Login sebagai user warga1
        self.client.post('/login', data={'username': 'warga1', 'password': 'warga123'}, follow_redirects=True)
        user = User.query.filter_by(username='warga1').first()
        self.assertIsNotNone(user.warga_id)

        # Cari tagihan warga tersebut
        unpaid = Iuran.query.filter_by(warga_id=user.warga_id, status='Belum Lunas').limit(2).all()
        if len(unpaid) < 2:
            for b in [8, 9]:
                i = Iuran(warga_id=user.warga_id, periode_bulan=b, periode_tahun=2024, jumlah=15000.0, status='Belum Lunas')
                db.session.add(i)
            db.session.commit()
            unpaid = Iuran.query.filter_by(warga_id=user.warga_id, status='Belum Lunas').limit(2).all()

        ids = [i.id for i in unpaid]
        res = self.client.post('/iuran/bayar-batch', data={
            'iuran_ids': ids,
            'metode_bayar': 'Transfer Bank',
            'catatan': 'Sudah transfer lewat BCA mobile'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        # Status harus Menunggu Konfirmasi
        updated = Iuran.query.filter(Iuran.id.in_(ids)).all()
        for u in updated:
            self.assertEqual(u.status, 'Menunggu Konfirmasi')
            self.assertTrue(u.kode_pembayaran.startswith('BATCH-'))
        print(f"[PASS] Warga bayar batch {len(ids)} bulan berhasil masuk status Menunggu Konfirmasi")

        # Cleanup
        for u in updated:
            u.status = 'Belum Lunas'
            u.kode_pembayaran = None
        db.session.commit()
        self.client.get('/logout', follow_redirects=True)

    def test_warga_cannot_pay_batch_for_other_warga(self):
        """Warga tidak diizinkan membayar batch yang berisi tagihan warga lain"""
        self.client.post('/login', data={'username': 'warga1', 'password': 'warga123'}, follow_redirects=True)
        user = User.query.filter_by(username='warga1').first()

        # Ambil tagihan milik orang lain
        other_iuran = Iuran.query.filter(Iuran.warga_id != user.warga_id, Iuran.status == 'Belum Lunas').first()
        if other_iuran:
            res = self.client.post('/iuran/bayar-batch', data={
                'iuran_ids': [other_iuran.id],
                'metode_bayar': 'Transfer Bank'
            }, follow_redirects=True)
            self.assertIn('Akses ditolak', res.data.decode('utf-8'))
            
            # Status iuran orang lain tidak boleh berubah
            chk = db.session.get(Iuran, other_iuran.id)
            self.assertEqual(chk.status, 'Belum Lunas')
            print("[PASS] Security check: Warga dilarang memproses iuran warga lain")

        self.client.get('/logout', follow_redirects=True)

    def test_kuitansi_batch(self):
        """Kuitansi batch menampilkan rincian multi-bulan dan total akumulasi"""
        self.client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)
        
        warga = Warga.query.filter_by(is_aktif=True).first()
        b_code = "BATCH-TEST-MULTI-2026"
        
        iur1 = Iuran(warga_id=warga.id, periode_bulan=11, periode_tahun=2023, jumlah=15000.0, status='Lunas', kode_pembayaran=b_code)
        iur2 = Iuran(warga_id=warga.id, periode_bulan=12, periode_tahun=2023, jumlah=15000.0, status='Lunas', kode_pembayaran=b_code)
        db.session.add_all([iur1, iur2])
        db.session.commit()

        res = self.client.get(f'/iuran/kuitansi/{iur1.id}')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')

        self.assertIn('2 Bulan Sekaligus', html)
        self.assertIn('30.000', html) # Rp 15.000 + Rp 15.000
        self.assertIn('BATCH', html)
        print("[PASS] Kuitansi batch berhasil menampilkan multi-bulan dan total Rp 30.000")

        # Cleanup
        db.session.delete(iur1)
        db.session.delete(iur2)
        db.session.commit()
        self.client.get('/logout', follow_redirects=True)

if __name__ == '__main__':
    unittest.main()
