import django.db.models.deletion
from django.db import migrations, models


def copy_direct_rate_plans(apps, schema_editor):
    ChannelRatePlan = apps.get_model("integrations", "ChannelRatePlan")
    RatePlanDay = apps.get_model("integrations", "RatePlanDay")

    booking_plans = ChannelRatePlan.objects.filter(sales_channel="booking_com")
    for booking_plan in booking_plans.iterator():
        direct_plan, created = ChannelRatePlan.objects.get_or_create(
            tenant_id=booking_plan.tenant_id,
            property_id=booking_plan.property_id,
            unit_id=booking_plan.unit_id,
            code=booking_plan.code,
            sales_channel="direct",
            defaults={
                "title": booking_plan.title,
                "default_rate": booking_plan.default_rate,
                "currency": booking_plan.currency,
                "is_active": booking_plan.is_active,
                "channex_room_type_id": "",
                "channex_rate_plan_id": "",
            },
        )
        if not created:
            continue

        day_rows = RatePlanDay.objects.filter(rate_plan_id=booking_plan.id)
        RatePlanDay.objects.bulk_create(
            [
                RatePlanDay(
                    tenant_id=day.tenant_id,
                    rate_plan_id=direct_plan.id,
                    date=day.date,
                    rate=day.rate,
                    min_stay_arrival=day.min_stay_arrival,
                    min_stay_through=day.min_stay_through,
                    max_stay=day.max_stay,
                    stop_sell=day.stop_sell,
                    closed_to_arrival=day.closed_to_arrival,
                    closed_to_departure=day.closed_to_departure,
                    synced_at=day.synced_at,
                )
                for day in day_rows.iterator(chunk_size=500)
            ],
            batch_size=500,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("integrations", "0018_channexmessage"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="channelrateplan",
            name="integrations_rateplan_unique_tenant_property_unit_code",
        ),
        migrations.RemoveConstraint(
            model_name="channelrateplan",
            name="integrations_rateplan_unique_tenant_channex_id",
        ),
        migrations.AddField(
            model_name="channelrateplan",
            name="sales_channel",
            field=models.CharField(
                choices=[
                    ("direct", "Direct / stay"),
                    ("booking_com", "Booking.com"),
                    ("airbnb", "Airbnb"),
                ],
                default="booking_com",
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="channelrateplan",
            name="channex_rate_plan_id",
            field=models.CharField(blank=True, default="", max_length=36),
        ),
        migrations.AlterField(
            model_name="channelrateplan",
            name="channex_room_type_id",
            field=models.CharField(blank=True, default="", max_length=36),
        ),
        migrations.AddConstraint(
            model_name="channelrateplan",
            constraint=models.UniqueConstraint(
                fields=("tenant", "property", "unit", "code", "sales_channel"),
                name="integrations_rateplan_unique_tenant_property_unit_code_channel",
            ),
        ),
        migrations.AddConstraint(
            model_name="channelrateplan",
            constraint=models.UniqueConstraint(
                condition=models.Q(("channex_rate_plan_id__gt", "")),
                fields=("tenant", "channex_rate_plan_id"),
                name="integrations_rateplan_unique_tenant_channex_id",
            ),
        ),
        migrations.RunPython(copy_direct_rate_plans, migrations.RunPython.noop),
    ]
