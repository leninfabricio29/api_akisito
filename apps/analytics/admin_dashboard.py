"""Contexto del dashboard del admin (UNFOLD['DASHBOARD_CALLBACK'])."""

import json
from datetime import timedelta

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.businesses.models import Business
from apps.checkins.models import CheckIn
from apps.loyalty.models import Membership
from apps.rewards.models import Redemption


def dashboard_callback(request, context):
    now = timezone.now()
    today = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    since = today - timedelta(days=13)

    checkins_today = CheckIn.objects.filter(created_at__gte=today)
    pending = Business.objects.filter(status=Business.Status.PENDING).select_related("owner", "category")[:10]

    daily = dict(
        CheckIn.objects.filter(status=CheckIn.Status.AWARDED, created_at__gte=since)
        .annotate(d=TruncDate("created_at"))
        .values("d")
        .annotate(c=Count("pk"))
        .values_list("d", "c")
    )
    days = [(since + timedelta(days=i)).date() for i in range(14)]

    suspicious = (
        CheckIn.objects.filter(status=CheckIn.Status.REJECTED, created_at__gte=now - timedelta(days=7))
        .values("client__email")
        .annotate(c=Count("pk"))
        .filter(c__gte=5)
        .order_by("-c")[:8]
    )

    context.update(
        {
            "kpis": [
                {"title": "Negocios pendientes", "value": Business.objects.filter(status=Business.Status.PENDING).count(),
                 "href": reverse("admin:businesses_business_changelist") + "?status__exact=pending", "icon": "pending_actions"},
                {"title": "Negocios activos", "value": Business.objects.approved().count(),
                 "href": reverse("admin:businesses_business_changelist") + "?status__exact=approved", "icon": "storefront"},
                {"title": "Clientes", "value": User.objects.filter(role=User.Role.CLIENT, is_active=True).count(),
                 "href": reverse("admin:accounts_user_changelist") + "?role__exact=client", "icon": "people"},
                {"title": "Check-ins hoy", "value": checkins_today.filter(status=CheckIn.Status.AWARDED).count(),
                 "href": reverse("admin:checkins_checkin_changelist"), "icon": "qr_code_scanner"},
                {"title": "Check-ins rechazados hoy", "value": checkins_today.filter(status=CheckIn.Status.REJECTED).count(),
                 "href": reverse("admin:checkins_checkin_changelist") + "?status__exact=rejected", "icon": "gpp_maybe"},
                {"title": "Canjes validados hoy",
                 "value": Redemption.objects.filter(status=Redemption.Status.VALIDATED, validated_at__gte=today).count(),
                 "href": reverse("admin:rewards_redemption_changelist"), "icon": "redeem"},
                {"title": "Puntos en circulación",
                 "value": Membership.objects.aggregate(v=Sum("points_balance"))["v"] or 0,
                 "href": reverse("admin:loyalty_membership_changelist"), "icon": "toll"},
            ],
            "checkins_chart": json.dumps(
                {
                    "labels": [d.strftime("%d/%m") for d in days],
                    "datasets": [{"label": "Check-ins", "data": [daily.get(d, 0) for d in days],
                                  "backgroundColor": "#cb3a7c", "borderRadius": 4}],
                }
            ),
            "pending_businesses": {
                "headers": ["Negocio", "RUC", "Verificador", "Categoría", "Registrado"],
                "rows": [
                    [
                        b.name, b.ruc, "✔" if b.ruc_checksum_ok else "⚠ revisar",
                        b.category.name, timezone.localtime(b.created_at).strftime("%d/%m/%Y %H:%M"),
                    ]
                    for b in pending
                ],
            },
            "suspicious_clients": {
                "headers": ["Cliente", "Rechazos (7 días)"],
                "rows": [[row["client__email"], row["c"]] for row in suspicious],
            },
        }
    )
    return context
