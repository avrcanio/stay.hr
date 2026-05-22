from django.db import migrations, models


def backfill_channel_timestamps(apps, schema_editor):
    Reservation = apps.get_model("reservations", "Reservation")
    for reservation in Reservation.objects.filter(
        import_source="booking_xls",
        imported_at__isnull=False,
    ):
        reservation.xls_imported_at = reservation.imported_at
        reservation.save(update_fields=["xls_imported_at"])

    for reservation in Reservation.objects.filter(
        import_source="smoobu",
        imported_at__isnull=False,
    ):
        reservation.smoobu_modified_at = reservation.imported_at
        if reservation.external_id:
            reservation.smoobu_booking_id = reservation.external_id
        reservation.save(update_fields=["smoobu_modified_at", "smoobu_booking_id"])


class Migration(migrations.Migration):
    dependencies = [
        ("reservations", "0006_merge_id_recognition_and_monthly_stats"),
    ]

    operations = [
        migrations.AddField(
            model_name="reservation",
            name="xls_imported_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="reservation",
            name="smoobu_modified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="reservation",
            name="smoobu_booking_id",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.RunPython(backfill_channel_timestamps, migrations.RunPython.noop),
    ]
