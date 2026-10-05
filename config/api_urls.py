"""
Rutas de la API v1.

Cliente:   auth, me, businesses, favorites, checkins, reviews, wallets, rewards, redemptions, notifications
Negocio:   business/* (perfil, QR, imágenes, recompensas, canjes, reseñas, clientes, estadísticas)
"""

from django.urls import include, path
from rest_framework.routers import SimpleRouter

from apps.analytics.views import BusinessStatsView
from apps.businesses import views as business_views
from apps.content.views import AppVersionView, BannerListView
from apps.loyalty import views as loyalty_views
from apps.notifications import views as notification_views
from apps.reviews import views as review_views
from apps.rewards import views as reward_views

router = SimpleRouter(trailing_slash=True)
router.register("businesses", business_views.BusinessViewSet, basename="business")
router.register("favorites", business_views.FavoriteViewSet, basename="favorite")
router.register("rewards", reward_views.RewardViewSet, basename="reward")
router.register("redemptions", reward_views.MyRedemptionViewSet, basename="redemption")
router.register("notifications", notification_views.NotificationViewSet, basename="notification")

business_router = SimpleRouter(trailing_slash=True)
business_router.register("qr", business_views.OwnBusinessQRViewSet, basename="own-business-qr")
business_router.register("rewards", reward_views.OwnRewardViewSet, basename="own-reward")
business_router.register("redemptions", reward_views.OwnRedemptionViewSet, basename="own-redemption")
business_router.register("reviews", review_views.OwnBusinessReviewViewSet, basename="own-review")

business_urls = [
    path("", business_views.OwnBusinessView.as_view(), name="own-business"),
    path("resubmit/", business_views.ResubmitBusinessView.as_view(), name="own-business-resubmit"),
    path("customers/", loyalty_views.CustomerListView.as_view(), name="own-customers"),
    path("stats/", BusinessStatsView.as_view(), name="own-stats"),
    *business_router.urls,
]

urlpatterns = [
    path("", include("apps.accounts.urls")),
    path("", include("apps.checkins.urls")),
    path("categories/", business_views.CategoryListView.as_view(), name="categories"),
    path("banners/", BannerListView.as_view(), name="banners"),
    path("app/version/", AppVersionView.as_view(), name="app-version"),
    path("businesses/<int:business_id>/reviews/", review_views.BusinessReviewsView.as_view(), name="business-reviews"),
    path("businesses/<int:business_id>/rewards/", reward_views.BusinessRewardsView.as_view(), name="business-rewards"),
    path("reviews/", review_views.MyReviewsView.as_view(), name="my-reviews"),
    path("wallets/", loyalty_views.WalletListView.as_view(), name="wallets"),
    path("wallets/<int:business_id>/transactions/", loyalty_views.WalletTransactionsView.as_view(), name="wallet-transactions"),
    path("devices/", notification_views.DeviceView.as_view(), name="devices"),
    path("business/", include(business_urls)),
    *router.urls,
]
