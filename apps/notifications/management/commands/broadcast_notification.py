from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User
from apps.notifications.models import Device, Notification
from apps.notifications.services import dispatch_pending, notify

DEFAULT_TITLE = "Gracias por ser parte de Akisito 💛"
DEFAULT_BODY = (
    "Nos mudamos de ciudad para seguir creciendo. Gracias por cada visita, cada punto y cada reseña: "
    "ustedes hicieron posible esta etapa. ¡Pronto les contaremos las novedades!"
)

AUDIENCES = {
    "clients": [User.Role.CLIENT],
    "businesses": [User.Role.BUSINESS],
    "all": [User.Role.CLIENT, User.Role.BUSINESS],
}


class Command(BaseCommand):
    help = (
        "Envía una notificación (en la app + push) a todos los usuarios activos. "
        "Ej: manage.py broadcast_notification --title '...' --body '...' --audience all --send-now"
    )

    def add_arguments(self, parser):
        parser.add_argument("--title", default=DEFAULT_TITLE, help="Máx. 120 caracteres.")
        parser.add_argument("--body", default=DEFAULT_BODY, help="Máx. 500 caracteres.")
        parser.add_argument("--audience", choices=AUDIENCES, default="clients")
        parser.add_argument("--no-push", action="store_true", help="Solo guarda la notificación en la app.")
        parser.add_argument(
            "--send-now", action="store_true", help="Despacha los push ya, sin esperar al cron dispatch_notifications."
        )
        parser.add_argument("--dry-run", action="store_true", help="Muestra a cuántos llegaría sin enviar nada.")
        parser.add_argument("--yes", action="store_true", help="No pedir confirmación.")

    def handle(self, *args, **opts):
        title, body = opts["title"].strip(), opts["body"].strip()
        if not title or not body:
            raise CommandError("El título y el mensaje no pueden estar vacíos.")
        if len(title) > 120 or len(body) > 500:
            raise CommandError(f"Muy largo: título {len(title)}/120, mensaje {len(body)}/500.")

        user_ids = list(
            User.objects.filter(role__in=AUDIENCES[opts["audience"]], is_active=True, deleted_at__isnull=True)
            .values_list("pk", flat=True)
        )
        devices = Device.objects.filter(user_id__in=user_ids, is_active=True).count()

        self.stdout.write(f"Título:   {title}\nMensaje:  {body}\n")
        self.stdout.write(f"Usuarios: {len(user_ids)} ({opts['audience']}) · dispositivos activos: {devices}")

        if not user_ids:
            self.stdout.write(self.style.WARNING("No hay destinatarios."))
            return
        if opts["dry_run"]:
            self.stdout.write(self.style.NOTICE("Dry run: no se envió nada."))
            return
        if not opts["yes"] and input("¿Enviar? [s/N] ").strip().lower() not in ("s", "si", "sí", "y", "yes"):
            self.stdout.write("Cancelado.")
            return

        send_push = not opts["no_push"]
        with transaction.atomic():
            created = notify(user_ids, title, body, Notification.Kind.SYSTEM, {}, send_push=send_push)
        self.stdout.write(self.style.SUCCESS(f"Notificaciones creadas: {created}"))

        if send_push and opts["send_now"]:
            pending = Notification.objects.filter(push_status=Notification.PushStatus.PENDING)
            total, remaining = 0, pending.count()
            while remaining:
                total += dispatch_pending(limit=2000)
                now_remaining = pending.count()
                if now_remaining >= remaining:  # sin avance: FCM falló, que lo reintente el cron
                    self.stdout.write(self.style.WARNING(f"Quedan {now_remaining} push pendientes; los enviará el cron."))
                    break
                remaining = now_remaining
            self.stdout.write(self.style.SUCCESS(f"Push enviados: {total}"))
        elif send_push:
            self.stdout.write("Los push quedan pendientes; los enviará dispatch_notifications en el próximo minuto.")
