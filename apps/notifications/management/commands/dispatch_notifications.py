from django.core.management.base import BaseCommand

from apps.notifications.services import dispatch_pending


class Command(BaseCommand):
    help = "Envía los push pendientes (campañas y envíos masivos). Ejecutar cada minuto."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=2000)

    def handle(self, *args, **options):
        sent = dispatch_pending(limit=options["limit"])
        self.stdout.write(self.style.SUCCESS(f"Push enviados: {sent}"))
