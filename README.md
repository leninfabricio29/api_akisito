# Akisito API

Backend de fidelización de clientes: el cliente escanea el QR del negocio, se valida su ubicación en el servidor,
gana puntos en ese negocio y se le invita a dejar una reseña por puntos extra. Los puntos se canjean por
recompensas del mismo negocio.

Django 6.1 · Django REST Framework · PostgreSQL · django-unfold (admin) · Cloudinary · Firebase Cloud Messaging.

## Puesta en marcha

```powershell
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env         # y completa los valores
python manage.py migrate
python manage.py seed_initial  # configuración de puntos + categorías
python manage.py createsuperuser
python manage.py runserver
```

- Admin: http://localhost:8000/admin/
- API: http://localhost:8000/api/v1/
- Salud: http://localhost:8000/health/

`manage.py` usa `config.settings.dev`; `wsgi.py`/`asgi.py` usan `config.settings.prod`, que exige
`DJANGO_SECRET_KEY` y un `JWT_SECRET` de al menos 32 caracteres.

## Pruebas

```powershell
$env:DJANGO_SETTINGS_MODULE="config.settings.test"; python manage.py test apps
```

La configuración de test usa almacenamiento en memoria, correo local y deshabilita Firebase.

## Estructura

```
config/
  settings/        base, dev, prod, test, unfold (menú del admin)
  api_urls.py      todas las rutas /api/v1/
apps/
  core/            modelos base, errores, permisos, validadores (cédula/RUC), geo, correo
  accounts/        usuario (cliente/negocio/admin), JWT, recuperación de contraseña
  businesses/      negocio (1 RUC = 1 local), categorías, imágenes, QR, favoritos
  loyalty/         membresía (puntos por negocio), libro de movimientos, reglas, retención
  checkins/        escaneo de QR con validación de ubicación
  reviews/         reseñas ligadas a una visita, respuesta del negocio, moderación
  rewards/         recompensas, canjes con código, validación y expiración
  notifications/   notificaciones en app + push FCM con cola
  analytics/       estadísticas del negocio y dashboard del admin
  content/         banners
templates/         correos HTML y dashboard del admin
```

Cada app separa `models`, `services` (reglas de negocio), `serializers`, `views` y `admin`.
Las vistas no contienen lógica de negocio: llaman a `services`.

## Tareas programadas (management commands)

| Command | Frecuencia | Qué hace |
|---|---|---|
| `dispatch_notifications` | cada minuto | Envía los push pendientes (campañas masivas) |
| `expire_redemptions` | cada 15 min | Expira canjes vencidos y devuelve los puntos |
| `send_winback` | diario 10:00 | Recuerda a clientes sin visitar un negocio en N días |
| `expire_points` | diario 03:00 | Vence saldos inactivos (solo si está activado en el admin) |

Linux (crontab):

```cron
* * * * *    cd /srv/akisito && .venv/bin/python manage.py dispatch_notifications
*/15 * * * * cd /srv/akisito && .venv/bin/python manage.py expire_redemptions
0 10 * * *   cd /srv/akisito && .venv/bin/python manage.py send_winback
0 3 * * *    cd /srv/akisito && .venv/bin/python manage.py expire_points
```

Windows (Programador de tareas):

```powershell
schtasks /Create /SC MINUTE /MO 15 /TN "Akisito expire_redemptions" /TR "C:\ruta\api_akisito\.venv\Scripts\python.exe C:\ruta\api_akisito\manage.py expire_redemptions"
```

Todos los commands son idempotentes: si una ejecución se salta o se solapa con otra, no se duplican reembolsos ni avisos.

## Reglas de negocio

Se editan en **Admin → Fidelización → Configuración de puntos**. Cada negocio puede sobrescribir los puntos y el radio.

| Regla | Por defecto |
|---|---|
| Puntos por visita / por reseña | 10 / 10 |
| Tiempo mínimo entre visitas con puntos (mismo negocio) | 4 h |
| Check-ins máximos por cliente al día (todos los negocios) | 10 |
| Radio del check-in / precisión GPS mínima | 150 m / 100 m |
| Plazo para reseñar tras la visita | 48 h |
| Reseñas con puntos por negocio | 1 cada 30 días (puede reseñar cada visita, sin puntos) |
| Recordatorio a clientes inactivos | 30 días |
| Vencimiento de puntos por inactividad | desactivado (365 días) |

Los puntos de la reseña no dependen de la calificación.

## Flujo de check-in

```
App: escanea QR ──► POST /api/v1/checkins/scan/ {qr, latitude, longitude, accuracy, is_mocked}
Servidor: QR válido → negocio aprobado → ubicación (simulada / precisión / radio)
          → límite diario → tiempo mínimo entre visitas → +puntos
Respuesta 201: {business, points_earned, balance, visits, review: {points, deadline}, checkin: {id}}
App: "¡Visitaste X! +10 pts. ¿Dejas una reseña? +10 pts" ──► POST /api/v1/reviews/ {checkin_id, rating, comment}
```

Errores de check-in (`code`): `invalid_qr` (404), `business_unavailable`, `checkin_mocked_location`,
`checkin_low_accuracy`, `checkin_out_of_range` (+`distance_m`), `checkin_daily_limit` (429),
`checkin_cooldown` (429, +`next_checkin_at`). Los rechazos se registran para detectar fraude en el admin.

## Endpoints

Todas las respuestas de error tienen la forma `{"detail", "code", "errors"?}`.
Los listados usan paginación `{count, next, previous, results}` (`?page=`, `?page_size=`).

**Autenticación y perfil**

| Método | Ruta | |
|---|---|---|
| POST | `auth/register/start/` | Registro, paso 1: `email` e `is_business`; envía un código de 6 dígitos |
| POST | `auth/register/verify/` | Registro, paso 2: valida `email` + `code` |
| POST | `auth/register/complete/` | Registro, paso 3: `email` + `code` + `password`; crea la cuenta y devuelve JWT |
| POST | `auth/login/` | `{email, password}` → `{access, refresh, user}` |
| POST | `auth/refresh/` | `{refresh}` → `{access, refresh}` |
| POST | `auth/password/forgot/` · `verify/` · `reset/` | Recuperación con código de 6 dígitos |
| POST | `auth/password/change/` | Cambio de contraseña |
| GET/PATCH/DELETE | `me/` | Perfil (`pending_steps`: pasos que la app obliga a completar, `profile` y `business`); DELETE elimina la cuenta (requiere `password`) |
| POST/DELETE | `devices/` | Registrar / desactivar token FCM |

**Cliente**

| Método | Ruta | |
|---|---|---|
| GET | `categories/` · `banners/` | Catálogos |
| GET | `app/version/` | Versión vigente por plataforma (`latest_version`, `min_version`, `store_url`); la app avisa o bloquea si la instalada es anterior |
| GET | `businesses/?search=&category=` | Directorio |
| GET | `businesses/?lat=&lng=&radius=` | Cercanos por distancia |
| GET | `businesses/{id}/` · `{id}/reviews/` · `{id}/rewards/` | Detalle, reseñas, recompensas |
| GET/POST/DELETE | `favorites/` · `favorites/{business_id}/` | Favoritos |
| POST | `checkins/scan/` | Escanear QR |
| GET | `checkins/?business=` | Mis visitas (`can_review`) |
| GET/POST | `reviews/` | Mis reseñas / reseñar una visita |
| GET | `wallets/` | Mis puntos por negocio + próxima recompensa |
| GET | `wallets/{business_id}/transactions/` | Movimientos |
| GET | `rewards/?business=` · POST `rewards/{id}/redeem/` | Recompensas y canje |
| GET | `redemptions/` · POST `redemptions/{id}/cancel/` | Mis canjes |
| GET | `notifications/` · `unread-count/` · POST `{id}/read/` · `read-all/` | Notificaciones |

**Negocio** (prefijo `business/`)

| Método | Ruta | |
|---|---|---|
| POST | `business/` | Alta del negocio tras registrarse (RUC validado, queda pendiente de aprobación) |
| GET/PATCH | `business/` | Perfil del negocio. `logo` y `cover` (portada) se suben por multipart. El RUC y el estado no se editan; la ubicación solo antes de la aprobación (`location_locked`) |
| POST | `business/resubmit/` | Reenviar a revisión tras un rechazo |
| GET | `business/qr/` · `qr/image/` · POST `qr/rotate/` | QR (solo aprobados) |
| CRUD | `business/rewards/` | Recompensas (notifica a miembros y favoritos) |
| GET | `business/redemptions/` · POST `redemptions/validate/` | Canjes y validación por código |
| GET | `business/reviews/` · POST `reviews/{id}/reply/` | Reseñas y respuestas |
| GET | `business/customers/?segment=new|frequent|at_risk|inactive` | Clientes |
| GET | `business/stats/?period=week|month|year` | Indicadores de fidelización |
