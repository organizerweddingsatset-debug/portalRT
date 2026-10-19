import unittest
from app import app, db
from models import User, Warga, Rumah

class UserTypesAndRolesTestCase(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.client = app.test_client()
        self.ctx = app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()

    def test_superadmin_is_not_warga(self):
        """Rule: (superadmin bukan warga)"""
        admin = User.query.filter_by(role='superadmin').first()
        self.assertIsNotNone(admin, "Superadmin account must exist")
        self.assertEqual(admin.user_type, 'superadmin')
        self.assertEqual(admin.role, 'superadmin')
        self.assertIsNone(admin.warga_id, "Superadmin warga_id MUST be None (Bukan Warga)")
        self.assertIsNone(admin.warga, "Superadmin relationship to Warga MUST be None")
        self.assertFalse(admin.is_warga(), "admin.is_warga() MUST return False")
        self.assertTrue(admin.is_superadmin(), "admin.is_superadmin() MUST return True")
        self.assertTrue(admin.is_admin(), "admin.is_admin() MUST return True")
        print("[PASS] Superadmin is verified as non-warga (warga_id=None, is_warga()=False)")

    def test_ketua_rt_is_warga_pemilik(self):
        """Ketua RT: Peran Ketua RT, Tipe Warga Pemilik"""
        ketua = User.query.filter(User.role.in_(['ketua_rt', 'pejabat'])).first()
        self.assertIsNotNone(ketua)
        self.assertEqual(ketua.user_type, 'warga_pemilik')
        self.assertTrue(ketua.is_ketua_rt())
        self.assertTrue(ketua.is_warga())
        self.assertTrue(ketua.is_warga_pemilik())
        self.assertIsNotNone(ketua.warga_id)
        self.assertIn("Bambang", ketua.warga.nama)
        print("[PASS] Ketua RT is verified as Warga Pemilik with household ties (Rumah A1/01)")

    def test_pengurus_is_warga_pemilik(self):
        """Pengurus: Peran Pengurus, Tipe Warga Pemilik"""
        pengurus = User.query.filter_by(role='pengurus').first()
        self.assertIsNotNone(pengurus)
        self.assertEqual(pengurus.user_type, 'warga_pemilik')
        self.assertTrue(pengurus.is_pengurus())
        self.assertTrue(pengurus.is_warga())
        self.assertIsNotNone(pengurus.warga_id)
        self.assertIn("Ahmad Fauzi", pengurus.warga.nama)
        print("[PASS] Pengurus (Bendahara) is verified as Warga Pemilik (Rumah A2/05)")

    def test_warga_pemilik_and_warga_kontrak(self):
        """Warga: Peran Warga, Tipe Warga Pemilik & Warga Kontrak"""
        # 1. Warga Pemilik (Budi Santoso)
        budi_user = User.query.filter_by(username='warga1').first()
        self.assertIsNotNone(budi_user)
        self.assertEqual(budi_user.role, 'warga')
        self.assertEqual(budi_user.user_type, 'warga_pemilik')
        self.assertTrue(budi_user.is_warga_pemilik())
        self.assertFalse(budi_user.is_warga_kontrak())
        self.assertTrue(budi_user.is_warga())

        # 2. Warga Kontrak (Ahmad Budiman Sujatmiko)
        ahmad_user = User.query.filter_by(username='AhmadG65').first()
        self.assertIsNotNone(ahmad_user)
        self.assertEqual(ahmad_user.role, 'warga')
        self.assertEqual(ahmad_user.user_type, 'warga_kontrak')
        self.assertTrue(ahmad_user.is_warga_kontrak())
        self.assertFalse(ahmad_user.is_warga_pemilik())
        self.assertTrue(ahmad_user.is_warga())
        print("[PASS] Clean distinction between Warga Pemilik and Warga Kontrak verified")

    def test_create_user_modal_logic(self):
        """Test creating user via route enforces non-warga for Superadmin"""
        self.client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)
        
        # Test creating new Superadmin with form
        res_admin = self.client.post('/pengaturan/users/tambah', data={
            'username': 'tech_sysadmin',
            'nama': 'Technical Support IT',
            'password': 'password123',
            'role': 'superadmin',
            'user_type': 'superadmin',
            'warga_id': '3', # Form might pass an id, but system must nullify it
            'no_hp': '089911223344'
        }, follow_redirects=True)
        self.assertEqual(res_admin.status_code, 200)

        tech_user = User.query.filter_by(username='tech_sysadmin').first()
        self.assertIsNotNone(tech_user)
        self.assertEqual(tech_user.role, 'superadmin')
        self.assertEqual(tech_user.user_type, 'superadmin')
        self.assertIsNone(tech_user.warga_id, "Superadmin MUST NOT be tied to any citizen")
        self.assertFalse(tech_user.is_warga())
        print("[PASS] User creation route strictly enforces Superadmin as non-warga")

        # Cleanup test user
        db.session.delete(tech_user)
        db.session.commit()

if __name__ == '__main__':
    unittest.main()
