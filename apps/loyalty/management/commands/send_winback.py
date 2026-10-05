from django.core.management.base import BaseCommand

from apps.loyalty.retention import send_winback


class Command(BaseCommand):
    help = "Envía recordatorios a clientes inactivos. Ejecutar a diario (p. ej. 10:00)."

    def handle(self, *args, **options):
        count = send_winback()
        self.stdout.write(self.style.SUCCESS(f"Recordatorios creados: {count}"))
