from django.core.management.base import BaseCommand

from apps.businesses.models import Category
from apps.loyalty.models import LoyaltySettings

CATEGORIES = [
    ("Restaurantes", "restaurant"),
    ("Cafeterías", "cafe"),
    ("Bares", "wine-bar"),
    ("Panaderías", "bakery"),
    ("Heladerías", "ice-cream"),
    ("Belleza y spa", "spa"),
    ("Gimnasios", "fitness"),
    ("Tiendas", "store"),
    ("Servicios", "construct"),
]


class Command(BaseCommand):
    help = "Crea la configuración de puntos y las categorías iniciales (idempotente)."

    def handle(self, *args, **options):
        LoyaltySettings.load()
        created = 0
        for order, (name, icon) in enumerate(CATEGORIES):
            _, was_created = Category.objects.get_or_create(name=name, defaults={"icon": icon, "order": order})
            created += was_created
        self.stdout.write(self.style.SUCCESS(f"Configuración lista. Categorías nuevas: {created}"))
