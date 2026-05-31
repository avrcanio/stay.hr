from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("integrations", "0019_channelrateplan_sales_channel"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="channelrateplan",
            options={"ordering": ["property_id", "unit_id", "sales_channel", "code"]},
        ),
    ]
