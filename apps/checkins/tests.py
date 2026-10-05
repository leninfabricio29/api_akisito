from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from apps.businesses.models import Business
from apps.core.testing import BUSINESS_LAT, BUSINESS_LNG, api_for, make_business, make_client
from apps.loyalty.models import LoyaltySettings, Membership, PointTransaction

from .models import CheckIn

URL = "/api/v1/checkins/scan/"


class ScanTests(TestCase):
    def setUp(self):
        self.client_user = make_client()
        self.business = make_business()
        self.api = api_for(self.client_user)

    def scan(self, **overrides):
        payload = {
            "qr": self.business.qr_payload,
            "latitude": float(BUSINESS_LAT),
            "longitude": float(BUSINESS_LNG),
            "accuracy": 15,
        }
        payload.update(overrides)
        return self.api.post(URL, payload, format="json")

    def test_scan_awards_points_and_invites_review(self):
        response = self.scan()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["points_earned"], 10)
        self.assertEqual(response.data["balance"], 10)
        self.assertEqual(response.data["review"]["points"], 10)
        membership = Membership.objects.get(client=self.client_user, business=self.business)
        self.assertEqual(membership.checkins_count, 1)
        self.assertEqual(PointTransaction.objects.filter(membership=membership, kind="checkin").count(), 1)

    def test_accepts_raw_token(self):
        self.assertEqual(self.scan(qr=self.business.qr_token).status_code, 201)

    def test_business_override_points(self):
        self.business.checkin_points = 25
        self.business.save()
        self.assertEqual(self.scan().data["points_earned"], 25)

    def test_out_of_range_is_rejected_and_logged(self):
        response = self.scan(latitude=float(BUSINESS_LAT) + 0.01)  # ~1.1 km
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "checkin_out_of_range")
        self.assertGreater(response.data["distance_m"], 1000)
        self.assertTrue(CheckIn.objects.filter(status="rejected", reject_reason="out_of_range").exists())
        self.assertFalse(Membership.objects.filter(client=self.client_user).exists())

    def test_mocked_location_rejected(self):
        response = self.scan(is_mocked=True)
        self.assertEqual(response.data["code"], "checkin_mocked_location")

    def test_low_accuracy_rejected(self):
        response = self.scan(accuracy=500)
        self.assertEqual(response.data["code"], "checkin_low_accuracy")

    def test_cooldown_blocks_second_scan(self):
        self.assertEqual(self.scan().status_code, 201)
        response = self.scan()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.data["code"], "checkin_cooldown")
        self.assertIn("next_checkin_at", response.data)
        self.assertEqual(Membership.objects.get(client=self.client_user).points_balance, 10)

    def test_frequent_visits_after_cooldown_keep_full_points(self):
        """Fidelización: volver no se castiga (antes la 2ª visita valía 33% y la 3ª se bloqueaba)."""
        start = timezone.now()
        for i in range(3):
            with mock.patch("django.utils.timezone.now", return_value=start + timedelta(hours=5 * i)):
                self.assertEqual(self.scan().status_code, 201)
        membership = Membership.objects.get(client=self.client_user)
        self.assertEqual(membership.points_balance, 30)
        self.assertEqual(membership.checkins_count, 3)

    def test_daily_limit(self):
        cfg = LoyaltySettings.load()
        cfg.max_checkins_per_day = 1
        cfg.save()
        other = make_business()
        self.assertEqual(self.scan().status_code, 201)
        response = self.scan(qr=other.qr_payload)
        self.assertEqual(response.data["code"], "checkin_daily_limit")

    def test_invalid_qr(self):
        response = self.scan(qr="akisito://checkin/nope")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["code"], "invalid_qr")

    def test_rotated_qr_stops_working(self):
        old = self.business.qr_payload
        self.business.rotate_qr()
        self.assertEqual(self.scan(qr=old).status_code, 404)

    def test_pending_business_unavailable(self):
        pending = make_business(status=Business.Status.PENDING)
        response = self.scan(qr=pending.qr_payload)
        self.assertEqual(response.data["code"], "business_unavailable")

    def test_business_user_cannot_scan(self):
        response = api_for(self.business.owner).post(URL, {"qr": "x", "latitude": 0, "longitude": 0}, format="json")
        self.assertEqual(response.status_code, 403)
