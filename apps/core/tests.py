from django.contrib import admin
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.core.testing import BUSINESS_LAT, BUSINESS_LNG, api_for, make_business, make_client
from apps.loyalty.models import Membership


class AdminSmokeTests(TestCase):
    """Todas las pantallas del admin cargan (changelist, detalle y dashboard)."""

    def setUp(self):
        self.admin = User.objects.create_superuser(email="admin@test.com", password="x")
        self.client.force_login(self.admin)
        business = make_business()
        user = make_client()
        api_for(user).post(
            "/api/v1/checkins/scan/",
            {"qr": business.qr_payload, "latitude": float(BUSINESS_LAT), "longitude": float(BUSINESS_LNG)},
            format="json",
        )
        make_business(status="pending")

    def test_dashboard(self):
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Negocios pendientes")

    def test_all_changelists_and_change_pages(self):
        for model, model_admin in admin.site._registry.items():
            opts = model._meta
            url = reverse(f"admin:{opts.app_label}_{opts.model_name}_changelist")
            response = self.client.get(url, follow=True)
            self.assertEqual(response.status_code, 200, url)
            obj = model.objects.first()
            if obj is not None:
                change = reverse(f"admin:{opts.app_label}_{opts.model_name}_change", args=[obj.pk])
                self.assertEqual(self.client.get(change).status_code, 200, change)

    def test_adjust_points_view(self):
        membership = Membership.objects.get()
        url = reverse("admin:loyalty_membership_adjust", args=[membership.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.post(url, {"points": -5, "description": "Corrección"})
        self.assertEqual(response.status_code, 302)
        membership.refresh_from_db()
        self.assertEqual(membership.points_balance, 5)

    def test_approve_via_change_form_notifies_owner(self):
        from apps.businesses.models import Business

        pending = Business.objects.get(status="pending")
        url = reverse("admin:businesses_business_change", args=[pending.pk])
        form = self.client.get(url).context["adminform"].form
        data = {k: v for k, v in form.initial.items() if v is not None and k not in ("logo", "cover")}
        data.update({
            "owner": pending.owner_id, "category": pending.category_id, "status": "approved",
        })
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302, getattr(response, "context", None) and response.context["adminform"].form.errors)
        pending.refresh_from_db()
        self.assertEqual(pending.status, "approved")
        self.assertIsNotNone(pending.reviewed_at)
        self.assertTrue(pending.owner.notifications.filter(kind="business").exists())
