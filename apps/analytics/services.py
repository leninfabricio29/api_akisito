"""Indicadores de fidelización para el panel del negocio."""

from datetime import timedelta

from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import ExtractHour, TruncDate, TruncMonth
from django.utils import timezone

from apps.checkins.models import CheckIn
from apps.loyalty.models import Membership, PointTransaction
from apps.loyalty.views import segment_filter
from apps.reviews.models import Review
from apps.rewards.models import Redemption

PERIODS = {"week": 7, "month": 30, "year": 365}


def _range(period: str, now):
    days = PERIODS[period]
    today_start = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    start = today_start - timedelta(days=days - 1)
    prev_start = start - timedelta(days=days)
    return start, prev_start


def _pct_change(current, previous):
    if not previous:
        return None
    return round((current - previous) * 100 / previous, 1)


def business_stats(business, period: str = "month", now=None) -> dict:
    now = now or timezone.now()
    start, prev_start = _range(period, now)

    awarded = CheckIn.objects.filter(business=business, status=CheckIn.Status.AWARDED)
    current = awarded.filter(created_at__gte=start)
    previous = awarded.filter(created_at__gte=prev_start, created_at__lt=start)

    visits, visits_prev = current.count(), previous.count()
    unique_clients = current.values("client").distinct().count()
    unique_prev = previous.values("client").distinct().count()

    memberships = Membership.objects.filter(business=business)
    new_clients = memberships.filter(first_checkin_at__gte=start).count()
    returning = max(unique_clients - new_clients, 0)

    reviews = Review.objects.filter(business=business, created_at__gte=start)
    review_agg = reviews.aggregate(count=Count("pk"), avg=Avg("rating"))

    redemptions = Redemption.objects.filter(business=business, status=Redemption.Status.VALIDATED)
    redeemed = redemptions.filter(validated_at__gte=start).count()
    redeemed_prev = redemptions.filter(validated_at__gte=prev_start, validated_at__lt=start).count()

    txns = PointTransaction.objects.filter(membership__business=business, created_at__gte=start)
    points = txns.aggregate(
        issued=Sum("points", filter=Q(kind__in=[PointTransaction.Kind.CHECKIN, PointTransaction.Kind.REVIEW])),
        spent=Sum("points", filter=Q(kind=PointTransaction.Kind.REDEMPTION)),
        refunded=Sum("points", filter=Q(kind=PointTransaction.Kind.REFUND)),
    )

    return {
        "period": period,
        "start": start,
        "end": now,
        "visits": {"value": visits, "previous": visits_prev, "change_pct": _pct_change(visits, visits_prev)},
        "unique_clients": {
            "value": unique_clients, "previous": unique_prev, "change_pct": _pct_change(unique_clients, unique_prev),
        },
        "new_clients": new_clients,
        "returning_clients": returning,
        "repeat_rate_pct": round(returning * 100 / unique_clients, 1) if unique_clients else 0,
        "visits_per_client": round(visits / unique_clients, 2) if unique_clients else 0,
        "reviews": {"count": review_agg["count"], "rating_avg": round(review_agg["avg"] or 0, 2)},
        "redemptions": {"value": redeemed, "previous": redeemed_prev, "change_pct": _pct_change(redeemed, redeemed_prev)},
        "points": {
            "issued": points["issued"] or 0,
            "redeemed": -((points["spent"] or 0) + (points["refunded"] or 0)),
            "outstanding": memberships.aggregate(v=Sum("points_balance"))["v"] or 0,
        },
        "segments": {
            name: memberships.filter(checkins_count__gt=0).filter(segment_filter(name, now)).count()
            for name in ("new", "frequent", "at_risk", "inactive")
        },
        "series": _series(current, period),
        "by_hour": _by_hour(current),
        "top_clients": _top_clients(current),
    }


def _series(queryset, period):
    trunc = TruncMonth("created_at") if period == "year" else TruncDate("created_at")
    rows = (
        queryset.annotate(bucket=trunc)
        .values("bucket")
        .annotate(visits=Count("pk"), clients=Count("client", distinct=True))
        .order_by("bucket")
    )
    return [
        {"date": row["bucket"].date() if hasattr(row["bucket"], "date") else row["bucket"],
         "visits": row["visits"], "clients": row["clients"]}
        for row in rows
    ]


def _by_hour(queryset):
    rows = dict(
        queryset.annotate(hour=ExtractHour("created_at")).values("hour").annotate(c=Count("pk")).values_list("hour", "c")
    )
    return [{"hour": h, "visits": rows.get(h, 0)} for h in range(24)]


def _top_clients(queryset, limit=5):
    rows = (
        queryset.values("client", "client__first_name", "client__last_name")
        .annotate(visits=Count("pk"))
        .order_by("-visits")[:limit]
    )
    return [
        {"id": r["client"], "name": f"{r['client__first_name']} {r['client__last_name']}".strip(), "visits": r["visits"]}
        for r in rows
    ]
