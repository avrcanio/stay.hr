from django.db import migrations, models


def migrate_import_source_forward(apps, schema_editor):
    Reservation = apps.get_model("reservations", "Reservation")
    Reservation.objects.filter(import_source="smoobu").update(import_source="channex")


class Migration(migrations.Migration):
    dependencies = [
        ("reservations", "0010_reservation_confirmation_pdf"),
    ]

    operations = [
        migrations.RunPython(migrate_import_source_forward, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="reservation",
            name="smoobu_booking_id",
        ),
        migrations.RenameField(
            model_name="reservation",
            old_name="smoobu_modified_at",
            new_name="channel_modified_at",
        ),
    ]
