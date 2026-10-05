from django.db import transaction
from django.db.models import Avg, Count, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.businesses.models import Business
from apps.checkins.models import CheckIn
from apps.checkins.services import pending_review_points
from apps.core.exceptions import ConflictError, DomainError
from apps.loyalty.models import PointTransaction
from apps.loyalty.services import apply_points, get_settings, lock_membership
from apps.notifications.models import Notification
from apps.notifications.services import notify

from .models import Review


def create_review(client, *, checkin_id: int, rating: int, comment: str = "") -> Review:
    with transaction.atomic():
        checkin = get_object_or_404(
            CheckIn.objects.select_for_update(of=("self",)).select_related("business__owner"),
            pk=checkin_id,
            client=client,
            status=CheckIn.Status.AWARDED,
        )
        if Review.objects.filter(checkin=checkin).exists():
            raise ConflictError("Ya dejaste una reseña para esta visita.")
        now = timezone.now()
        if not checkin.review_window_open(now):
            raise DomainError("El plazo para reseñar esta visita terminó.", code="review_window_closed")

        business = checkin.business
        cfg = get_settings()
        membership = lock_membership(client, business)
        points = pending_review_points(client, business, cfg, now)

        review = Review.objects.create(
            checkin=checkin, client=client, business=business, rating=rating, comment=comment.strip(),
            points_awarded=points,
        )
        if points:
            apply_points(membership, points, PointTransaction.Kind.REVIEW, f"Reseña en {business.name}", review=review)
        membership.reviews_count += 1
        membership.save(update_fields=["reviews_count", "updated_at"])
        refresh_business_rating(business.pk)

        notify(
            business.owner,
            f"Nueva reseña {'★' * rating}",
            f"{client.first_name} calificó tu negocio con {rating}/5." + (f" “{comment[:80]}”" if comment else ""),
            Notification.Kind.REVIEW,
            {"review_id": review.pk},
        )
    return review


def reply(business: Business, review_id: int, text: str) -> Review:
    with transaction.atomic():
        review = get_object_or_404(Review.objects.select_for_update(), pk=review_id, business=business)
        first_reply = not review.reply
        review.reply = text.strip()
        review.replied_at = timezone.now()
        review.save(update_fields=["reply", "replied_at", "updated_at"])
        if first_reply:
            notify(
                review.client,
                f"{business.name} respondió tu reseña",
                text[:200],
                Notification.Kind.REVIEW,
                {"business_id": business.pk, "review_id": review.pk},
            )
    return review


def set_visibility(review: Review, *, hidden: bool, note: str = "") -> Review:
    review.status = Review.Status.HIDDEN if hidden else Review.Status.PUBLISHED
    review.moderation_note = note
    review.save(update_fields=["status", "moderation_note", "updated_at"])
    refresh_business_rating(review.business_id)
    return review


def refresh_business_rating(business_id: int) -> None:
    """Recalcula promedio y conteo en una sola sentencia SQL (solo reseñas publicadas)."""
    published = Review.objects.filter(business=OuterRef("pk"), status=Review.Status.PUBLISHED).values("business")
    Business.objects.filter(pk=business_id).update(
        rating_avg=Coalesce(Subquery(published.annotate(v=Avg("rating")).values("v")[:1]), Value(0.0)),
        rating_count=Coalesce(Subquery(published.annotate(c=Count("pk")).values("c")[:1]), Value(0)),
    )


def rating_breakdown(business_id: int) -> dict:
    qs = Review.objects.filter(business_id=business_id, status=Review.Status.PUBLISHED)
    counts = qs.aggregate(**{f"s{i}": Count("pk", filter=Q(rating=i)) for i in range(1, 6)})
    return {str(i): counts[f"s{i}"] for i in range(1, 6)}
