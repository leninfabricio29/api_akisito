from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsBusinessOwner

from .services import PERIODS, business_stats


class BusinessStatsView(APIView):
    """GET /business/stats/?period=week|month|year"""

    permission_classes = [IsBusinessOwner]

    def get(self, request):
        period = request.query_params.get("period", "month")
        if period not in PERIODS:
            raise ValidationError({"period": f"Usa uno de: {', '.join(PERIODS)}."})
        return Response(business_stats(request.user.business, period))
