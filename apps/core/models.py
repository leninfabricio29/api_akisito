from django.db import models


class TimeStampedModel(models.Model):
    """Base abstracta con marcas de creación y actualización."""

    created_at = models.DateTimeField("creado", auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField("actualizado", auto_now=True)

    class Meta:
        abstract = True


class SingletonModel(models.Model):
    """Modelo de una sola fila (configuraciones editables desde el admin)."""

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        return (0, {})

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
