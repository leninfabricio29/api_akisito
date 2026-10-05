from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from apps.core.testing import BUSINESS_LAT, BUSINESS_LNG, api_for, make_business, make_client
from apps.loyalty.models import Membership

from .models import Review


class ReviewTests(TestCase):
    def setUp(self):
        self.user = make_client()
        self.business = make_business()
        self.api = api_for(self.user)

    def checkin(self, at=None):
        payload = {"qr": self.business.qr_payload, "latitude": float(BUSINESS_LAT), "longitude": float(BUSINESS_LNG)}
        with mock.patch("django.utils.timezone.now", return_value=at or timezone.now()):
            response = self.api.post("/api/v1/checkins/scan/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data["checkin"]["id"]

    def review(self, checkin_id, rating=5, comment="Excelente atención"):
        return self.api.post(
            "/api/v1/reviews/", {"checkin_id": checkin_id, "rating": rating, "comment": comment}, format="json"
        )

    def test_review_awards_points_and_updates_rating(self):
        response = self.review(self.checkin(), rating=4)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["points_awarded"], 10)
        self.assertEqual(Membership.objects.get(client=self.user).points_balance, 20)
        self.business.refresh_from_db()
        self.assertEqual(self.business.rating_count, 1)
        self.assertEqual(float(self.business.rating_avg), 4.0)

    def test_low_rating_earns_the_same_points(self):
        self.assertEqual(self.review(self.checkin(), rating=1).data["points_awarded"], 10)

    def test_one_review_per_checkin(self):
        checkin_id = self.checkin()
        self.review(checkin_id)
        self.assertEqual(self.review(checkin_id).status_code, 409)

    def test_review_requires_own_checkin(self):
        other = make_client()
        checkin_id = self.checkin()
        response = api_for(other).post("/api/v1/reviews/", {"checkin_id": checkin_id, "rating": 5}, format="json")
        self.assertEqual(response.status_code, 404)

    def test_review_window_closes(self):
        checkin_id = self.checkin()
        with mock.patch("django.utils.timezone.now", return_value=timezone.now() + timedelta(hours=49)):
            response = self.review(checkin_id)
        self.assertEqual(response.data["code"], "review_window_closed")

    def test_second_review_within_30_days_earns_no_points(self):
        now = timezone.now()
        self.review(self.checkin(now))
        second = self.checkin(now + timedelta(hours=5))
        with mock.patch("django.utils.timezone.now", return_value=now + timedelta(hours=6)):
            response = self.review(second)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["points_awarded"], 0)

    def test_hidden_review_excluded_from_rating(self):
        from . import services

        self.review(self.checkin(), rating=1)
        services.set_visibility(Review.objects.get(), hidden=True)
        self.business.refresh_from_db()
        self.assertEqual(self.business.rating_count, 0)
        public = api_for().get(f"/api/v1/businesses/{self.business.pk}/reviews/")
        self.assertEqual(public.data["count"], 0)

    def test_business_reply_notifies_client(self):
        self.review(self.checkin())
        review = Review.objects.get()
        response = api_for(self.business.owner).post(
            f"/api/v1/business/reviews/{review.pk}/reply/", {"reply": "¡Gracias por venir!"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(self.user.notifications.filter(kind="review").exists())
