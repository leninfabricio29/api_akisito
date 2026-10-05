from django.db import migrations


def first_image_to_cover(apps, schema_editor):
    """La portada era la primera foto de la galería: se conserva como el nuevo campo `cover`."""
    Business = apps.get_model("businesses", "Business")
    BusinessImage = apps.get_model("businesses", "BusinessImage")
    for business in Business.objects.filter(cover=""):
        first = BusinessImage.objects.filter(business=business).order_by("order", "id").first()
        if first and first.image:
            business.cover = first.image.name
            business.save(update_fields=["cover"])


class Migration(migrations.Migration):
    dependencies = [("businesses", "0003_business_cover")]

    operations = [migrations.RunPython(first_image_to_cover, migrations.RunPython.noop)]
