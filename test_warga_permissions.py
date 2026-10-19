from app import app, db
from models import User, Warga

def test_warga_own_view_and_edit():
    with app.app_context():
        with app.test_client() as client:
            # 1. Login as warga1 (Budi Santoso)
            login_res = client.post('/login', data={'username': 'warga1', 'password': 'warga123'}, follow_redirects=True)
            assert login_res.status_code == 200
            print("[PASS] Login as warga1 succeeded")

            # 2. View /warga: must be OWN VIEW
            warga_view = client.get('/warga')
            assert warga_view.status_code == 200
            assert b"Data Kependudukan Keluarga Anda" in warga_view.data or b"Data Keluarga Saya" in warga_view.data
            print("[PASS] /warga shows OWN family data only")

            # 3. View own profile /warga/<own_id>
            user_warga1 = User.query.filter_by(username='warga1').first()
            budi = user_warga1.warga
            assert budi is not None
            own_detail = client.get(f'/warga/{budi.id}')
            assert own_detail.status_code == 200
            assert b"Edit Data Saya" in own_detail.data
            print("[PASS] Own detail displays 'Edit Data Saya' button")

            # 4. Edit own profile
            edit_post = client.post(f'/warga/edit/{budi.id}', data={
                'nama': 'Budi Santoso',
                'jenis_kelamin': budi.jenis_kelamin,
                'tempat_lahir': budi.tempat_lahir,
                'tanggal_lahir': budi.tanggal_lahir.strftime('%Y-%m-%d') if budi.tanggal_lahir else '',
                'agama': budi.agama,
                'pekerjaan': 'Software Engineering Lead',
                'status_perkawinan': budi.status_perkawinan,
                'no_rumah': 'B3/12',
                'alamat': budi.alamat,
                'no_hp': '085799998888',
                'email': 'budi.new@gmail.com'
            }, follow_redirects=True)
            assert edit_post.status_code == 200
            
            # Verify DB updated
            budi_refreshed = db.session.get(Warga, budi.id)
            assert budi_refreshed.pekerjaan == 'Software Engineering Lead'
            assert budi_refreshed.no_hp == '085799998888'
            print("[PASS] Warga successfully edited OWN profile data!")

            # 5. Try to view ANOTHER citizen outside family
            other_warga = Warga.query.filter(Warga.no_kk != budi.no_kk).first()
            forbidden_view = client.get(f'/warga/{other_warga.id}', follow_redirects=True)
            assert b"Akses ditolak" in forbidden_view.data
            print(f"[PASS] Access to other citizen ({other_warga.nama}) properly BLOCKED for warga role!")

            # 6. Try to edit ANOTHER citizen outside family
            forbidden_edit = client.post(f'/warga/edit/{other_warga.id}', data={
                'nama': 'Hacked Name',
                'pekerjaan': 'Hacked Job'
            }, follow_redirects=True)
            assert b"Akses ditolak" in forbidden_edit.data
            other_warga_refreshed = db.session.get(Warga, other_warga.id)
            assert other_warga_refreshed.nama != 'Hacked Name'
            print("[PASS] Tampering with other citizens' data properly REJECTED!")

            # 7. Try to delete citizen as warga
            forbidden_delete = client.post(f'/warga/hapus/{other_warga.id}', follow_redirects=True)
            assert b"Akses ditolak" in forbidden_delete.data
            assert db.session.get(Warga, other_warga.id) is not None
            print("[PASS] Deleting citizen as warga properly PREVENTED!")

            # 8. Login as Admin and verify unrestricted access
            client.get('/logout')
            admin_login = client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)
            admin_warga = client.get('/warga')
            assert admin_warga.status_code == 200
            assert b"51" in admin_warga.data
            print("[PASS] Admin retains full view of all citizens and administrative powers")

            # 9. Test Superadmin (Bukan Warga) can view all 204 dues but has no personal dues
            admin_iuran_all = client.get('/iuran')
            assert admin_iuran_all.status_code == 200
            assert b"Seluruh Warga RT 09" in admin_iuran_all.data
            assert b"204" in admin_iuran_all.data  # Total tagihan all warga
            assert b"Superadmin: Bukan Warga RT" in admin_iuran_all.data
            print("[PASS] Superadmin (Bukan Warga) can manage all 204 RT dues records and is marked as Non-Warga")

            # 9b. Test Ketua RT (Warga Pemilik) has dual-view and can check personal household dues
            client.get('/logout')
            client.post('/login', data={'username': 'ketua_rt', 'password': 'pejabat123'}, follow_redirects=True)
            ketua_iuran_saya = client.get('/iuran?view=saya')
            assert ketua_iuran_saya.status_code == 200
            assert b"Iuran Pribadi Pengurus" in ketua_iuran_saya.data
            assert b"H. Bambang Sutrisno" in ketua_iuran_saya.data
            assert b"A1/01" in ketua_iuran_saya.data
            print("[PASS] Ketua RT (Warga Pemilik) can toggle and check personal household dues for A1/01")

            # 10. Test Regular Warga cannot bypass own-view via ?view=semua
            client.get('/logout')
            client.post('/login', data={'username': 'warga1', 'password': 'warga123'}, follow_redirects=True)
            warga_iuran_attempt = client.get('/iuran?view=semua')
            assert warga_iuran_attempt.status_code == 200
            assert b"Menampilkan <strong>204</strong>" not in warga_iuran_attempt.data  # MUST NOT leak 204 records
            assert b"Budi Santoso" in warga_iuran_attempt.data
            print("[PASS] Regular citizen is strictly restricted to own household dues, ignoring ?view=semua")

            print("\nALL OWN-VIEW AND OWN-EDIT PERMISSION TESTS PASSED!")

if __name__ == '__main__':
    test_warga_own_view_and_edit()
