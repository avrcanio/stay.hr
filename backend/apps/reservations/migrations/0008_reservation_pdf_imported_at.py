from django.db import migrations, models


def backfill_pdf_imports(apps, schema_editor):
    Reservation = apps.get_model("reservations", "Reservation")
    for reservation in Reservation.objects.filter(
        import_source="booking_xls",
        xls_imported_at__isnull=False,
    ):
        reservation.pdf_imported_at = reservation.xls_imported_at
        reservation.import_source = "booking_pdf"
        reservation.save(update_fields=["pdf_imported_at", "import_source"])


class Migration(migrations.Migration):
    dependencies = [
        ("reservations", "0007_reservation_channel_timestamps"),
    ]

    operations = [
        migrations.AddField(
            model_name="reservation",
            name="pdf_imported_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_pdf_imports, migrations.RunPython.noop),
    ]
