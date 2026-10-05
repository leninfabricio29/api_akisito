from django.core.management.base import BaseCommand

from apps.rewards.services import expire_pending


class Command(BaseCommand):
    help = "Expira los canjes pendientes vencidos y devuelve los puntos. Ejecutar cada hora (o cada 15 min)."

    def handle(self, *args, **options):
        count = expire_pending()
        self.stdout.write(self.style.SUCCESS(f"Canjes expirados y reembolsados: {count}"))
