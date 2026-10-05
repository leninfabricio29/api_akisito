"""Configuración del panel administrativo (django-unfold)."""

from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _


def _link(title, icon, model_url, badge=None):
    item = {"title": title, "icon": icon, "link": reverse_lazy(model_url)}
    if badge:
        item["badge"] = badge
    return item


UNFOLD = {
    "SITE_TITLE": "Akisito Admin",
    "SITE_HEADER": "Akisito",
    "SITE_SUBHEADER": _("Fidelización de clientes"),
    "SITE_SYMBOL": "loyalty",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
    "SHOW_BACK_BUTTON": True,
    "DASHBOARD_CALLBACK": "apps.analytics.admin_dashboard.dashboard_callback",
    "COLORS": {
        "primary": {
            "50": "oklch(97.1% .014 343.198)",
            "100": "oklch(94.8% .028 342.258)",
            "200": "oklch(89.9% .061 343.231)",
            "300": "oklch(82.3% .12 346.018)",
            "400": "oklch(71.8% .202 349.761)",
            "500": "oklch(65.6% .241 354.308)",
            "600": "oklch(59.2% .249 .584)",
            "700": "oklch(52.5% .223 3.958)",
            "800": "oklch(45.9% .187 3.815)",
            "900": "oklch(40.8% .153 2.432)",
            "950": "oklch(28.4% .109 3.907)",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "title": _("General"),
                "items": [
                    {"title": _("Dashboard"), "icon": "dashboard", "link": reverse_lazy("admin:index")},
                ],
            },
            {
                "title": _("Negocios"),
                "items": [
                    _link(_("Negocios"), "storefront", "admin:businesses_business_changelist",
                          badge="apps.businesses.admin.pending_businesses_badge"),
                    _link(_("Categorías"), "category", "admin:businesses_category_changelist"),
                    _link(_("Favoritos"), "favorite", "admin:businesses_favorite_changelist"),
                ],
            },
            {
                "title": _("Fidelización"),
                "items": [
                    _link(_("Check-ins"), "qr_code_scanner", "admin:checkins_checkin_changelist"),
                    _link(_("Membresías"), "card_membership", "admin:loyalty_membership_changelist"),
                    _link(_("Movimientos de puntos"), "receipt_long", "admin:loyalty_pointtransaction_changelist"),
                    _link(_("Reseñas"), "reviews", "admin:reviews_review_changelist"),
                    _link(_("Configuración de puntos"), "tune", "admin:loyalty_loyaltysettings_changelist"),
                ],
            },
            {
                "title": _("Recompensas"),
                "items": [
                    _link(_("Recompensas"), "redeem", "admin:rewards_reward_changelist"),
                    _link(_("Canjes"), "confirmation_number", "admin:rewards_redemption_changelist"),
                ],
            },
            {
                "title": _("Comunicación"),
                "items": [
                    _link(_("Notificaciones"), "notifications", "admin:notifications_notification_changelist"),
                    _link(_("Dispositivos"), "smartphone", "admin:notifications_device_changelist"),
                    _link(_("Banners"), "campaign", "admin:content_banner_changelist"),
                    _link(_("Versión de la app"), "system_update", "admin:content_appversion_changelist"),
                ],
            },
            {
                "title": _("Usuarios"),
                "items": [
                    _link(_("Usuarios"), "people", "admin:accounts_user_changelist"),
                    _link(_("Grupos"), "group", "admin:auth_group_changelist"),
                ],
            },
        ],
    },
}
