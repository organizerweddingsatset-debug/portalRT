from app import app, db
from models import User, Warga, Iuran, TransaksiKas, Surat, Pengumuman, Inventaris, Laporan

def run_tests():
    with app.test_client() as client:
        # 1. Test Login page
        res = client.get('/login')
        assert res.status_code == 200, f"Login page failed: {res.status_code}"
        print("[PASS] Login page returns 200 OK")

        # 2. Test Login authentication as admin
        login_res = client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)
        assert login_res.status_code == 200, f"Login failed: {login_res.status_code}"
        assert b"Total Kas" in login_res.data, "Dashboard content missing"
        assert b"1.215.000" in login_res.data, "Total Kas figure matching screenshot missing"
        assert b"51 orang" in login_res.data, "Total Warga 51 orang missing"
        assert b"Pengumuman RT" in login_res.data, "Pengumuman RT missing"
        assert b"Ringkasan RT" in login_res.data, "Ringkasan RT missing"
        print("[PASS] Dashboard rendered matching screenshot figures (Total Kas: 1.215.000, 51 orang, Ringkasan RT)")

        # 3. Test Data Warga
        w_res = client.get('/warga')
        assert w_res.status_code == 200, "Warga index failed"
        assert b"Data Warga RT 09" in w_res.data
        print("[PASS] Data Warga route returns 200 OK")

        # 4. Test Iuran Warga
        i_res = client.get('/iuran')
        assert i_res.status_code == 200, "Iuran index failed"
        assert b"Iuran Warga" in i_res.data or b"Iuran Saya" in i_res.data
        print("[PASS] Iuran Warga route returns 200 OK")

        # 5. Test Transaksi Kas
        k_res = client.get('/kas')
        assert k_res.status_code == 200, "Kas index failed"
        assert b"Transaksi Kas" in k_res.data
        print("[PASS] Transaksi Kas route returns 200 OK")

        # 6. Test Persuratan
        s_res = client.get('/persuratan')
        assert s_res.status_code == 200, "Persuratan index failed"
        assert b"Persuratan" in s_res.data
        print("[PASS] Persuratan route returns 200 OK")

        # 7. Test Pengumuman
        p_res = client.get('/pengumuman')
        assert p_res.status_code == 200, "Pengumuman index failed"
        assert b"Pengumuman" in p_res.data
        print("[PASS] Pengumuman route returns 200 OK")

        # 8. Test Inventaris
        inv_res = client.get('/inventaris')
        assert inv_res.status_code == 200, "Inventaris index failed"
        assert b"Inventaris" in inv_res.data
        print("[PASS] Inventaris route returns 200 OK")

        # 9. Test Pelaporan
        lap_res = client.get('/pelaporan')
        assert lap_res.status_code == 200, "Pelaporan index failed"
        assert b"Pelaporan" in lap_res.data
        print("[PASS] Pelaporan route returns 200 OK")

        # 10. Test Pengaturan
        cfg_res = client.get('/pengaturan')
        assert cfg_res.status_code == 200, "Pengaturan index failed"
        assert b"Pengaturan" in cfg_res.data
        print("[PASS] Pengaturan route returns 200 OK")

        # 11. Test Ganti Password page
        pwd_res = client.get('/profil/ganti-password')
        assert pwd_res.status_code == 200, "Ganti password page failed"
        assert b"Ganti" in pwd_res.data
        print("[PASS] Ganti Password route returns 200 OK")

        # 12. Test Cetak Surat
        cetak_surat = client.get('/persuratan/cetak/1')
        assert cetak_surat.status_code == 200, "Cetak surat failed"
        assert b"RUKUN TETANGGA 09" in cetak_surat.data
        print("[PASS] Cetak Surat template returns 200 OK")

        # 13. Test Cetak Laporan Keuangan
        cetak_kas = client.get('/kas/laporan')
        assert cetak_kas.status_code == 200, "Cetak kas failed"
        assert b"LAPORAN KAS & KEUANGAN" in cetak_kas.data
        print("[PASS] Cetak Laporan Keuangan template returns 200 OK")

        print("\nALL 13 TESTS PASSED PERFECTLY!")

if __name__ == '__main__':
    run_tests()
