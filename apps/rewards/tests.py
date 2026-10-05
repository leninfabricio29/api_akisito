from datetime import timedelta
from unittest import mock

from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from apps.core.testing import api_for, make_business, make_client
from apps.loyalty.models import Membership, PointTransaction
from apps.loyalty.services import apply_points, lock_membership

from . import services
from .models import Redemption, Reward


def give_points(client, business, points):
    with transaction.atomic():
        membership = lock_membership(client, business)
        apply_points(membership, points, PointTransaction.Kind.ADJUSTMENT, "test")


class RedemptionTests(TestCase):
    def setUp(self):
        self.user = make_client()
        self.business = make_business()
        self.reward = Reward.objects.create(business=self.business, title="Café gratis", points_required=50)
        self.api = api_for(self.user)

    def redeem(self, reward=None):
        return self.api.post(f"/api/v1/rewards/{(reward or self.reward).pk}/redeem/")

    def balance(self, business=None):
        return Membership.objects.get(client=self.user, business=business or self.business).points_balance

    def test_insufficient_points(self):
        give_points(self.user, self.business, 20)
        response = self.redeem()
        self.assertEqual(response.data["code"], "insufficient_points")
        self.assertEqual(response.data["points_missing"], 30)

    def test_points_are_per_business(self):
        other = make_business()
        give_points(self.user, other, 100)
        self.assertEqual(self.redeem().data["code"], "insufficient_points")

    def test_redeem_and_validate(self):
        give_points(self.user, self.business, 60)
        response = self.redeem()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.balance(), 10)
        code = response.data["code"]

        business_api = api_for(self.business.owner)
        validated = business_api.post("/api/v1/business/redemptions/validate/", {"code": code.lower()}, format="json")
        self.assertEqual(validated.status_code, 200, validated.data)
        self.assertEqual(validated.data["status"], "validated")
        again = business_api.post("/api/v1/business/redemptions/validate/", {"code": code}, format="json")
        self.assertEqual(again.data["code"], "redemption_not_pending")

    def test_other_business_cannot_validate(self):
        give_points(self.user, self.business, 60)
        code = self.redeem().data["code"]
        intruder = make_business()
        response = api_for(intruder.owner).post("/api/v1/business/redemptions/validate/", {"code": code}, format="json")
        self.assertEqual(response.status_code, 404)

    def test_expire_refunds_and_frees_limit(self):
        """Antes: un canje expirado seguía contando para el límite por usuario."""
        give_points(self.user, self.business, 50)
        self.redeem()
        later = timezone.now() + timedelta(days=2)
        with mock.patch("django.utils.timezone.now", return_value=later):
            self.assertEqual(services.expire_pending(), 1)
        self.assertEqual(self.balance(), 50)
        self.reward.refresh_from_db()
        self.assertEqual(self.reward.redeemed_count, 0)
        self.assertEqual(self.redeem().status_code, 201)

    def test_validating_expired_code_refunds(self):
        give_points(self.user, self.business, 50)
        code = self.redeem().data["code"]
        with mock.patch("django.utils.timezone.now", return_value=timezone.now() + timedelta(days=2)):
            response = api_for(self.business.owner).post(
                "/api/v1/business/redemptions/validate/", {"code": code}, format="json"
            )
        self.assertEqual(response.data["code"], "redemption_expired")
        self.assertEqual(self.balance(), 50)
        self.assertEqual(Redemption.objects.get().status, "expired")

    def test_cancel_refunds(self):
        give_points(self.user, self.business, 50)
        redemption_id = self.redeem().data["id"]
        response = self.api.post(f"/api/v1/redemptions/{redemption_id}/cancel/")
        self.assertEqual(response.data["status"], "cancelled")
        self.assertEqual(self.balance(), 50)

    def test_max_per_client(self):
        give_points(self.user, self.business, 200)
        self.assertEqual(self.redeem().status_code, 201)
        self.assertEqual(self.redeem().data["code"], "redeem_limit")

    def test_stock(self):
        self.reward.stock = 1
        self.reward.max_per_client = None
        self.reward.save()
        give_points(self.user, self.business, 200)
        self.assertEqual(self.redeem().status_code, 201)
        self.assertEqual(self.redeem().data["code"], "reward_sold_out")

    def test_wallet_shows_next_reward(self):
        give_points(self.user, self.business, 30)
        response = self.api.get("/api/v1/wallets/")
        wallet = response.data["results"][0]
        self.assertEqual(wallet["points_balance"], 30)
        self.assertEqual(wallet["next_reward"]["points_missing"], 20)

    def test_new_reward_notifies_members(self):
        give_points(self.user, self.business, 1)
        with self.captureOnCommitCallbacks(execute=True):
            response = api_for(self.business.owner).post(
                "/api/v1/business/rewards/", {"title": "Postre gratis", "points_required": 80}, format="json"
            )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(self.user.notifications.filter(kind="reward").exists())


class LookupTests(TestCase):
    def test_lookup_before_validate(self):
        user, business = make_client(), make_business()
        reward = Reward.objects.create(business=business, title="Postre", points_required=10)
        give_points(user, business, 10)
        code = api_for(user).post(f"/api/v1/rewards/{reward.pk}/redeem/").data["code"]
        owner = api_for(business.owner)
        found = owner.get("/api/v1/business/redemptions/lookup/", {"code": code.lower()})
        self.assertEqual(found.status_code, 200)
        self.assertEqual(found.data["status"], "pending")
        self.assertEqual(found.data["reward"]["title"], "Postre")
        self.assertEqual(api_for(make_business().owner).get("/api/v1/business/redemptions/lookup/", {"code": code}).status_code, 404)


class AdminDeletionTests(TestCase):
    """Antes: el admin no dejaba borrar usuarios con canjes, movimientos o membresías."""

    def setUp(self):
        from apps.accounts.models import User

        self.admin = User.objects.create_superuser(email="root@test.com", password="Clave-segura-123")
        self.client.force_login(self.admin)
        self.user = make_client()
        business = make_business()
        reward = Reward.objects.create(business=business, title="Café gratis", points_required=50)
        give_points(self.user, business, 100)
        api_for(self.user).post(f"/api/v1/rewards/{reward.pk}/redeem/")
        self.assertEqual(Redemption.objects.count(), 1)

    def test_bulk_delete_client_with_history(self):
        from apps.accounts.models import User

        response = self.client.post(
            "/admin/accounts/user/",
            {"action": "delete_selected", "_selected_action": [self.user.pk], "post": "yes"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertEqual(Membership.objects.count(), 0)
        self.assertEqual(PointTransaction.objects.count(), 0)
        self.assertEqual(Redemption.objects.count(), 0)

    def test_delete_membership(self):
        membership = Membership.objects.get()
        response = self.client.post(f"/admin/loyalty/membership/{membership.pk}/delete/", {"post": "yes"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Membership.objects.count(), 0)
        self.assertEqual(Redemption.objects.count(), 0)

    def test_single_point_transaction_cannot_be_deleted(self):
        tx = PointTransaction.objects.first()
        self.client.post(f"/admin/loyalty/pointtransaction/{tx.pk}/delete/", {"post": "yes"})
        self.assertTrue(PointTransaction.objects.filter(pk=tx.pk).exists())

    def test_bulk_delete_business_owner(self):
        from apps.accounts.models import User
        from apps.businesses.models import Business

        business = Business.objects.get()
        owner = business.owner
        response = self.client.post(
            "/admin/accounts/user/",
            {"action": "delete_selected", "_selected_action": [owner.pk], "post": "yes"},
        )
        ctx = response.context or {}
        self.assertEqual(response.status_code, 302, (ctx.get("perms_lacking"), ctx.get("protected")))
        self.assertFalse(User.objects.filter(pk=owner.pk).exists())
        self.assertFalse(Business.objects.exists())
        self.assertFalse(Reward.objects.exists())
        self.assertEqual(Redemption.objects.count(), 0)
        self.assertEqual(Membership.objects.count(), 0)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
