from django.core.management.base import BaseCommand

from apps.loyalty.services import expire_inactive_points


class Command(BaseCommand):
    help = "Vence el saldo de membresías sin actividad (si está habilitado en la configuración). Ejecutar a diario."

    def handle(self, *args, **options):
        count = expire_inactive_points()
        self.stdout.write(self.style.SUCCESS(f"Membresías con puntos vencidos: {count}"))
