"""Fábricas para pruebas."""

import itertools
from decimal import Decimal

from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.tokens import tokens_for
from apps.businesses.models import Business, Category

_seq = itertools.count(1)

# Plaza Grande, Quito
BUSINESS_LAT = Decimal("-0.220000")
BUSINESS_LNG = Decimal("-78.512000")


def make_cedula(seed: int) -> str:
    base = f"17{seed % 10_000_000:07d}"[:9]
    total = 0
    for i, coef in enumerate((2, 1, 2, 1, 2, 1, 2, 1, 2)):
        product = int(base[i]) * coef
        total += product - 9 if product > 9 else product
    return base + str((10 - total % 10) % 10)


def make_private_ruc(seed: int) -> str:
    base = f"179{seed % 100_000:05d}"  # 8 dígitos únicos por seed; el 9º se ajusta hasta que el verificador exista
    coefs = (4, 3, 2, 7, 6, 5, 4, 3, 2)
    for digit in range(10):
        candidate = base + str(digit)
        remainder = sum(int(candidate[i]) * c for i, c in enumerate(coefs)) % 11
        check = 0 if remainder == 0 else 11 - remainder
        if check != 10:
            return candidate + str(check) + "001"
    raise AssertionError("no se pudo generar RUC")


def make_client(**extra) -> User:
    n = next(_seq)
    defaults = {"first_name": "Ana", "last_name": f"Cliente{n}", "phone": "0999999999", "ci": make_cedula(n)}
    defaults.update(extra)
    return User.objects.create_user(email=f"client{n}@test.com", password="Clave-segura-123", **defaults)


def make_business(status=Business.Status.APPROVED, **extra) -> Business:
    n = next(_seq)
    owner = User.objects.create_user(
        email=f"biz{n}@test.com", password="Clave-segura-123", first_name="Beto", last_name=f"Dueño{n}",
        role=User.Role.BUSINESS,
    )
    category, _ = Category.objects.get_or_create(name="Cafeterías")
    defaults = {
        "name": f"Café {n}", "ruc": make_private_ruc(n), "taxpayer_type": "private", "category": category,
        "address": "Av. Siempre Viva", "latitude": BUSINESS_LAT, "longitude": BUSINESS_LNG, "status": status,
    }
    defaults.update(extra)
    return Business.objects.create(owner=owner, **defaults)


def api_for(user=None) -> APIClient:
    client = APIClient()
    if user:
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens_for(user)['access']}")
    return client
