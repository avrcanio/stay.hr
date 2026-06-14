from django.db import migrations, models


def migrate_smoobu_data_forward(apps, schema_editor):
    IntegrationConfig = apps.get_model("integrations", "IntegrationConfig")
    UnitAvailabilityBlock = apps.get_model("integrations", "UnitAvailabilityBlock")

    IntegrationConfig.objects.filter(provider="smoobu").delete()
    UnitAvailabilityBlock.objects.filter(created_via="hospira").update(created_via="stay")


def _unitavailabilityblock_has_column(cursor, column_name: str, vendor: str) -> bool:
    table = "integrations_unitavailabilityblock"
    if vendor == "postgresql":
        cursor.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
            """,
            [table, column_name],
        )
        return cursor.fetchone() is not None
    cursor.execute(f"PRAGMA table_info('{table}')")
    return any(row[1] == column_name for row in cursor.fetchall())


def rename_block_column_if_needed(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    with schema_editor.connection.cursor() as cursor:
        if not _unitavailabilityblock_has_column(cursor, "smoobu_booking_id", vendor):
            return
        cursor.execute(
            "ALTER TABLE integrations_unitavailabilityblock "
            "RENAME COLUMN smoobu_booking_id TO block_ref"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0016_demo_channex_inventory_mode"),
    ]

    operations = [
        migrations.RunPython(migrate_smoobu_data_forward, migrations.RunPython.noop),
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    rename_block_column_if_needed, migrations.RunPython.noop
                ),
            ],
            state_operations=[
                migrations.RenameField(
                    model_name="unitavailabilityblock",
                    old_name="smoobu_booking_id",
                    new_name="block_ref",
                ),
            ],
        ),
        migrations.RemoveConstraint(
            model_name="unitavailabilityblock",
            name="integrations_unitblock_unique_tenant_smoobu_id",
        ),
        migrations.AddConstraint(
            model_name="unitavailabilityblock",
            constraint=models.UniqueConstraint(
                fields=("tenant", "block_ref"),
                name="integrations_unitblock_unique_tenant_block_ref",
            ),
        ),
        migrations.AlterField(
            model_name="unitavailabilityblock",
            name="reservation",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="availability_blocks",
                to="reservations.reservation",
            ),
        ),
        migrations.AlterField(
            model_name="unitavailabilityblock",
            name="created_via",
            field=models.CharField(
                choices=[("stay", "stay.hr")],
                default="stay",
                max_length=16,
            ),
        ),
        migrations.DeleteModel(
            name="UnitRateDay",
        ),
        migrations.AlterField(
            model_name="integrationconfig",
            name="provider",
            field=models.CharField(
                choices=[
                    ("booking", "Booking"),
                    ("email", "Email"),
                    ("ical", "iCal"),
                    ("evisitor", "eVisitor"),
                    ("channex", "Channex"),
                    ("whatsapp", "WhatsApp"),
                    ("other", "Other"),
                ],
                max_length=20,
            ),
        ),
    ]
