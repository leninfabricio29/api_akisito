from django.test import TestCase

from apps.core.testing import api_for

from .models import AppVersion


class AppVersionTests(TestCase):
    def test_public_endpoint_returns_both_platforms(self):
        config = AppVersion.load()
        config.android_latest_version = "1.2.0"
        config.android_min_version = "1.1.0"
        config.save()
        data = api_for().get("/api/v1/app/version/").data
        self.assertEqual(data["android"]["latest_version"], "1.2.0")
        self.assertEqual(data["android"]["min_version"], "1.1.0")
        self.assertIn("play.google.com", data["android"]["store_url"])
        self.assertIsNone(data["ios"]["min_version"])
        self.assertIsNone(data["ios"]["store_url"])
        self.assertTrue(data["message"])

    def test_admin_opens_singleton(self):
        from apps.accounts.models import User

        admin = User.objects.create_superuser(email="root@test.com", password="Clave-segura-123")
        self.client.force_login(admin)
        response = self.client.get("/admin/content/appversion/", follow=True)
        self.assertEqual(response.status_code, 200)
