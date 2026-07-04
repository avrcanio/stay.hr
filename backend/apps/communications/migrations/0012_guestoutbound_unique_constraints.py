# Migration C — dedupe backfill artifacts, then unique constraints (zero-downtime step 3)

from __future__ import annotations

from django.db import migrations, models


def dedupe_provider_message_ids(apps, schema_editor):
    GuestOutboundMessage = apps.get_model("communications", "GuestOutboundMessage")

    seen: set[tuple[str, str]] = set()
    dupes = (
        GuestOutboundMessage.objects.filter(provider_message_id__gt="")
        .order_by("provider", "provider_message_id", "id")
        .values_list("id", "provider", "provider_message_id")
    )
    clear_ids: list[int] = []
    for pk, provider, wamid in dupes:
        key = (provider, wamid)
        if key in seen:
            clear_ids.append(pk)
        else:
            seen.add(key)
    if clear_ids:
        GuestOutboundMessage.objects.filter(pk__in=clear_ids).update(
            provider="",
            provider_message_id="",
        )


def dedupe_draft_channel(apps, schema_editor):
    GuestOutboundMessage = apps.get_model("communications", "GuestOutboundMessage")

    seen: set[tuple[int, str]] = set()
    dupes = (
        GuestOutboundMessage.objects.filter(draft_id__isnull=False)
        .order_by("draft_id", "channel", "id")
        .values_list("id", "draft_id", "channel")
    )
    clear_draft_ids: list[int] = []
    for pk, draft_id, channel in dupes:
        key = (draft_id, channel)
        if key in seen:
            clear_draft_ids.append(pk)
        else:
            seen.add(key)
    if clear_draft_ids:
        GuestOutboundMessage.objects.filter(pk__in=clear_draft_ids).update(draft_id=None)


class Migration(migrations.Migration):

    dependencies = [
        ("communications", "0011_backfill_outbound_provider_message_id"),
    ]

    operations = [
        migrations.RunPython(dedupe_provider_message_ids, migrations.RunPython.noop),
        migrations.RunPython(dedupe_draft_channel, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="guestoutboundmessage",
            constraint=models.UniqueConstraint(
                condition=models.Q(("provider_message_id__gt", "")),
                fields=("provider", "provider_message_id"),
                name="guest_outbound_unique_provider_message_id",
            ),
        ),
        migrations.AddConstraint(
            model_name="guestoutboundmessage",
            constraint=models.UniqueConstraint(
                condition=models.Q(("draft__isnull", False)),
                fields=("draft", "channel"),
                name="guest_outbound_unique_draft_channel",
            ),
        ),
    ]
