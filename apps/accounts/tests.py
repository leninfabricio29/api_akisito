import re

from django.core import mail
from django.test import TestCase

from apps.businesses.models import Business, Category
from apps.core.testing import api_for, make_cedula, make_client, make_private_ruc
from apps.core.validators import validate_cedula, validate_ruc
from apps.notifications.models import Device

from .models import User

PASSWORD = "Clave-segura-123"


class ValidatorTests(TestCase):
    def test_valid_cedula(self):
        self.assertEqual(validate_cedula(make_cedula(12345)), make_cedula(12345))

    def test_invalid_cedula(self):
        from django.core.exceptions import ValidationError

        bad = make_cedula(1)[:9] + str((int(make_cedula(1)[9]) + 1) % 10)
        with self.assertRaises(ValidationError):
            validate_cedula(bad)

    def test_ruc_types(self):
        self.assertEqual(validate_ruc(make_cedula(7) + "001").taxpayer_type, "natural")
        info = validate_ruc(make_private_ruc(42))
        self.assertEqual(info.taxpayer_type, "private")
        self.assertTrue(info.checksum_ok)

    def test_private_ruc_bad_checksum_is_flagged_not_blocked(self):
        ruc = make_private_ruc(42)
        tampered = ruc[:9] + str((int(ruc[9]) + 1) % 10) + ruc[10:]
        self.assertFalse(validate_ruc(tampered).checksum_ok)


class RegistrationTests(TestCase):
    def setUp(self):
        self.api = api_for()

    def start(self, email, is_business=False):
        response = self.api.post("/api/v1/auth/register/start/", {"email": email, "is_business": is_business})
        self.assertEqual(response.status_code, 200, response.data)
        return re.search(r"(\d{6})", mail.outbox[-1].body).group(1)

    def complete(self, email, code, password=PASSWORD):
        return self.api.post(
            "/api/v1/auth/register/complete/", {"email": email, "code": code, "password": password}, format="json"
        )

    def test_client_signup_with_email_only(self):
        code = self.start("ANA@Test.com")
        verify = self.api.post("/api/v1/auth/register/verify/", {"email": "ana@test.com", "code": code})
        self.assertTrue(verify.data["valid"])
        response = self.complete("ana@test.com", code)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIn("access", response.data)
        self.assertEqual(response.data["user"]["email"], "ana@test.com")
        self.assertEqual(response.data["user"]["role"], "client")
        self.assertEqual(response.data["user"]["pending_steps"], ["profile"])
        self.assertTrue(User.objects.get(email="ana@test.com").check_password(PASSWORD))

    def test_code_is_single_use(self):
        code = self.start("uno@test.com")
        self.assertEqual(self.complete("uno@test.com", code).status_code, 201)
        self.assertEqual(self.complete("uno@test.com", code).data["code"], "invalid_signup_code")

    def test_wrong_code_does_not_create_account(self):
        code = self.start("dos@test.com")
        wrong = "000000" if code != "000000" else "111111"
        self.assertEqual(self.complete("dos@test.com", wrong).status_code, 400)
        self.assertFalse(User.objects.filter(email="dos@test.com").exists())

    def test_code_locked_after_failed_attempts(self):
        code = self.start("tres@test.com")
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(5):
            self.api.post("/api/v1/auth/register/verify/", {"email": "tres@test.com", "code": wrong})
        self.assertEqual(self.complete("tres@test.com", code).data["code"], "invalid_signup_code")

    def test_new_code_invalidates_previous(self):
        first = self.start("cuatro@test.com")
        second = self.start("cuatro@test.com")
        if first != second:
            self.assertEqual(self.complete("cuatro@test.com", first).status_code, 400)
        self.assertEqual(self.complete("cuatro@test.com", second).status_code, 201)

    def test_existing_email_is_rejected(self):
        user = make_client()
        response = self.api.post("/api/v1/auth/register/start/", {"email": user.email})
        self.assertEqual(response.data["code"], "email_taken")
        self.assertEqual(len(mail.outbox), 0)

    def test_weak_password_rejected(self):
        code = self.start("cinco@test.com")
        response = self.complete("cinco@test.com", code, password="12345678")
        self.assertEqual(response.status_code, 400)
        self.assertIn("password", response.data["errors"])

    def test_extra_fields_cannot_escalate_role(self):
        code = self.start("seis@test.com")
        response = self.api.post(
            "/api/v1/auth/register/complete/",
            {"email": "seis@test.com", "code": code, "password": PASSWORD, "role": "admin", "is_business": True},
            format="json",
        )
        self.assertEqual(response.data["user"]["role"], "client")

    def test_business_signup_then_business_profile(self):
        code = self.start("bar@test.com", is_business=True)
        response = self.complete("bar@test.com", code)
        self.assertEqual(response.data["user"]["role"], "business")
        self.assertEqual(response.data["user"]["pending_steps"], ["profile", "business"])

        owner = User.objects.get(email="bar@test.com")
        api = api_for(owner)
        api.patch("/api/v1/me/", {"first_name": "Beto", "last_name": "Z", "phone": "0999"}, format="json")
        category = Category.objects.create(name="Bares")
        payload = {"name": "Bar Z", "ruc": make_private_ruc(7), "category": category.pk,
                   "address": "Calle 1", "latitude": "-0.18", "longitude": "-78.48"}
        created = api.post("/api/v1/business/", payload, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data["status"], "pending")
        self.assertEqual(Business.objects.get().taxpayer_type, "private")
        self.assertEqual(api.get("/api/v1/me/").data["pending_steps"], [])
        again = api.post("/api/v1/business/", {**payload, "ruc": make_private_ruc(8)}, format="json")
        self.assertEqual(again.status_code, 409)

    def test_business_invalid_ruc(self):
        code = self.start("b@test.com", is_business=True)
        self.complete("b@test.com", code)
        category = Category.objects.create(name="Bares")
        response = api_for(User.objects.get(email="b@test.com")).post(
            "/api/v1/business/",
            {"name": "Bar", "ruc": "1234567890123", "category": category.pk,
             "address": "C", "latitude": "0", "longitude": "0"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("ruc", response.data["errors"])

    def test_client_cannot_create_business(self):
        response = api_for(make_client()).post("/api/v1/business/", {}, format="json")
        self.assertEqual(response.status_code, 403)

    def test_profile_names_cannot_be_blanked(self):
        user = make_client()
        response = api_for(user).patch("/api/v1/me/", {"first_name": ""}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_login_is_case_insensitive(self):
        user = make_client()
        response = api_for().post("/api/v1/auth/login/", {"email": user.email.upper(), "password": PASSWORD})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["user"]["id"], user.pk)


class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = make_client()
        self.api = api_for()

    def request_code(self):
        self.api.post("/api/v1/auth/password/forgot/", {"email": self.user.email})
        return re.search(r"(\d{6})", mail.outbox[-1].body).group(1)

    def test_unknown_email_same_response(self):
        response = self.api.post("/api/v1/auth/password/forgot/", {"email": "nadie@test.com"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("email", response.data)
        self.assertEqual(len(mail.outbox), 0)

    def test_full_reset(self):
        code = self.request_code()
        self.assertTrue(self.api.post("/api/v1/auth/password/verify/", {"email": self.user.email, "code": code}).data["valid"])
        response = self.api.post(
            "/api/v1/auth/password/reset/", {"email": self.user.email, "code": code, "new_password": "Otra-clave-456"}
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Otra-clave-456"))
        again = self.api.post(
            "/api/v1/auth/password/reset/", {"email": self.user.email, "code": code, "new_password": "Otra-clave-789"}
        )
        self.assertEqual(again.status_code, 400)

    def test_code_locked_after_failed_attempts(self):
        code = self.request_code()
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(5):
            self.api.post("/api/v1/auth/password/verify/", {"email": self.user.email, "code": wrong})
        response = self.api.post("/api/v1/auth/password/verify/", {"email": self.user.email, "code": code})
        self.assertEqual(response.data["code"], "invalid_reset_code")


class DeviceTests(TestCase):
    def test_token_moves_to_new_user(self):
        """Antes: el mismo teléfono con otra cuenta fallaba por token duplicado."""
        first, second = make_client(), make_client()
        api_for(first).post("/api/v1/devices/", {"token": "tok-1", "platform": "android"})
        response = api_for(second).post("/api/v1/devices/", {"token": "tok-1", "platform": "android"})
        self.assertEqual(response.status_code, 204, getattr(response, "data", None))
        self.assertEqual(Device.objects.get(token="tok-1").user, second)


class AccountDeletionTests(TestCase):
    def test_delete_account(self):
        user = make_client()
        response = api_for(user).delete("/api/v1/me/", {"password": PASSWORD}, format="json")
        self.assertEqual(response.status_code, 204)
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertIsNone(user.ci)
        self.assertFalse(User.objects.filter(email__startswith="client").filter(pk=user.pk).exists())
