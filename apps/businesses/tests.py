import time
from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from apps.core.testing import BUSINESS_LAT, BUSINESS_LNG, api_for, make_business, make_client
from apps.loyalty.retention import send_winback

from .models import Business


class DirectoryTests(TestCase):
    def setUp(self):
        self.near = make_business(name="Café Cerca")
        self.far = make_business(name="Café Lejos", latitude=BUSINESS_LAT + 1)
        make_business(name="Pendiente", status=Business.Status.PENDING)

    def test_only_approved_listed(self):
        names = {b["name"] for b in api_for().get("/api/v1/businesses/").data["results"]}
        self.assertEqual(names, {"Café Cerca", "Café Lejos"})

    def test_nearby_sorted_by_distance(self):
        response = api_for().get(
            "/api/v1/businesses/", {"lat": float(BUSINESS_LAT), "lng": float(BUSINESS_LNG), "radius": 2000}
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([b["name"] for b in response.data["results"]], ["Café Cerca"])
        self.assertEqual(response.data["results"][0]["distance_m"], 0)

    def test_client_sees_favorite_and_points(self):
        user = make_client()
        api = api_for(user)
        self.assertEqual(api.post("/api/v1/favorites/", {"business_id": self.near.pk}).status_code, 201)
        self.assertEqual(api.post("/api/v1/favorites/", {"business_id": self.near.pk}).status_code, 409)
        detail = api.get(f"/api/v1/businesses/{self.near.pk}/").data
        self.assertTrue(detail["is_favorite"])
        self.assertEqual(api.delete(f"/api/v1/favorites/{self.near.pk}/").status_code, 204)

    def test_pending_business_cannot_get_qr(self):
        pending = Business.objects.get(name="Pendiente")
        self.assertEqual(api_for(pending.owner).get("/api/v1/business/qr/").status_code, 403)
        self.assertEqual(api_for(self.near.owner).get("/api/v1/business/qr/image/").status_code, 200)

    def test_owner_cannot_edit_ruc_or_status(self):
        api = api_for(self.near.owner)
        response = api.patch("/api/v1/business/", {"ruc": "0000000000001", "status": "approved", "name": "Nuevo"})
        self.assertEqual(response.status_code, 200, response.data)
        self.near.refresh_from_db()
        self.assertEqual(self.near.name, "Nuevo")
        self.assertNotEqual(self.near.ruc, "0000000000001")

    def test_stats_endpoint(self):
        user = make_client()
        api_for(user).post(
            "/api/v1/checkins/scan/",
            {"qr": self.near.qr_payload, "latitude": float(BUSINESS_LAT), "longitude": float(BUSINESS_LNG)},
            format="json",
        )
        stats = api_for(self.near.owner).get("/api/v1/business/stats/", {"period": "week"}).data
        self.assertEqual(stats["visits"]["value"], 1)
        self.assertEqual(stats["new_clients"], 1)
        self.assertEqual(stats["points"]["outstanding"], 10)
        customers = api_for(self.near.owner).get("/api/v1/business/customers/", {"segment": "new"}).data
        self.assertEqual(customers["count"], 1)


class WinbackTests(TestCase):
    def test_winback_sent_once_per_inactivity(self):
        business = make_business()
        user = make_client()
        api_for(user).post(
            "/api/v1/checkins/scan/",
            {"qr": business.qr_payload, "latitude": float(BUSINESS_LAT), "longitude": float(BUSINESS_LNG)},
            format="json",
        )
        later = timezone.now() + timedelta(days=31)
        self.assertEqual(send_winback(later), 1)
        self.assertEqual(send_winback(later + timedelta(days=1)), 0)
        with mock.patch("django.utils.timezone.now", return_value=later):
            self.assertTrue(user.notifications.filter(kind="winback").exists())


class QrPosterTests(TestCase):
    def test_poster_link_works_and_expires(self):
        business = make_business(name="Café Afiche")
        url = api_for(business.owner).post("/api/v1/business/qr/poster/").data["url"]
        path = url.split("testserver")[-1]
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Café Afiche")
        self.assertContains(response, "data:image/png;base64,")
        with mock.patch("django.core.signing.time.time", return_value=time.time() + 3600):
            self.assertEqual(self.client.get(path).status_code, 410)

    def test_pending_business_cannot_get_poster(self):
        pending = make_business(status=Business.Status.PENDING)
        self.assertEqual(api_for(pending.owner).post("/api/v1/business/qr/poster/").status_code, 403)


class OwnBusinessProfileTests(TestCase):
    def test_location_editable_while_pending(self):
        business = make_business(status=Business.Status.PENDING)
        response = api_for(business.owner).patch(
            "/api/v1/business/", {"latitude": "-0.180000", "longitude": "-78.480000", "address": "Otra calle"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data["location_locked"])

    def test_location_locked_after_approval(self):
        business = make_business()
        api = api_for(business.owner)
        moved = api.patch("/api/v1/business/", {"latitude": "-0.180000", "longitude": "-78.480000"}, format="json")
        self.assertEqual(moved.status_code, 400)
        self.assertIn("latitude", moved.data["errors"])
        same = api.patch(
            "/api/v1/business/",
            {"latitude": str(business.latitude), "longitude": str(business.longitude), "address": "Referencia nueva"},
            format="json",
        )
        self.assertEqual(same.status_code, 200, same.data)
        self.assertTrue(same.data["location_locked"])

    def test_cover_is_its_own_field(self):
        business = make_business(cover="businesses/covers/portada.jpg")
        data = api_for().get(f"/api/v1/businesses/{business.pk}/").data
        self.assertTrue(data["cover"].endswith("portada.jpg"))
        self.assertNotIn("images", data)
        self.assertNotIn("website", data)


class NewBusinessAnnouncementTests(TestCase):
    def setUp(self):
        from apps.accounts.models import User

        self.clients = [make_client(), make_client()]
        self.inactive = make_client(is_active=False)
        self.other_business = make_business()
        self.pending = make_business(status=Business.Status.PENDING)
        self.admin = User.objects.create_superuser(email="root@test.com", password="Clave-segura-123")

    def announcements(self):
        from apps.notifications.models import Notification

        return Notification.objects.filter(kind=Notification.Kind.NEW_BUSINESS)

    def test_approval_notifies_only_active_clients(self):
        from apps.businesses import services

        services.set_status(self.pending, Business.Status.APPROVED, by=self.admin)
        notified = set(self.announcements().values_list("user_id", flat=True))
        self.assertEqual(notified, {c.pk for c in self.clients})
        self.assertEqual(self.announcements().first().data, {"business_id": self.pending.pk})
        self.pending.refresh_from_db()
        self.assertIsNotNone(self.pending.announced_at)

    def test_registration_and_rejection_do_not_notify(self):
        from apps.businesses import services

        services.set_status(self.pending, Business.Status.REJECTED, reason="RUC no coincide", by=self.admin)
        self.assertFalse(self.announcements().exists())

    def test_reapproval_is_not_announced_again(self):
        from apps.businesses import services

        services.set_status(self.pending, Business.Status.APPROVED, by=self.admin)
        services.set_status(self.pending, Business.Status.SUSPENDED, reason="Revisión", by=self.admin)
        services.set_status(self.pending, Business.Status.APPROVED, by=self.admin)
        self.assertEqual(self.announcements().count(), len(self.clients))
