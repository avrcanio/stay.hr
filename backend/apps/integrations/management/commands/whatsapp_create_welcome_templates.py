import json

from django.core.management.base import BaseCommand, CommandError

from apps.integrations.whatsapp.config import (
    access_token_from_env,
    meta_app_id_from_env,
    waba_id_from_env,
)
from apps.integrations.whatsapp.meta_templates import (
    MetaTemplateApiError,
    create_message_template,
    find_message_template,
    upload_template_header_from_url,
)
from apps.integrations.whatsapp.welcome_template_definitions import (
    DEFAULT_WELCOME_HEADER_IMAGE_URL,
    WELCOME_TEMPLATE_DEFINITIONS,
    WelcomeTemplateDefinition,
    build_welcome_template_payload,
)


class Command(BaseCommand):
    help = (
        "Create WhatsApp welcome templates (stay_welcome_*) on Meta WABA via Graph API "
        "and submit them for approval."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--language",
            action="append",
            dest="languages",
            default=[],
            help="Language code(s) to create: hr, en, de, es, fr. Default: all.",
        )
        parser.add_argument(
            "--waba-id",
            default="",
            help="WhatsApp Business Account ID (or WHATSAPP_WABA_ID env).",
        )
        parser.add_argument(
            "--access-token",
            default="",
            help="Meta access token (or WHATSAPP_ACCESS_TOKEN env). Never commit.",
        )
        parser.add_argument(
            "--app-id",
            default="",
            help="Meta App ID for header upload (or META_APP_ID env).",
        )
        parser.add_argument(
            "--header-image-url",
            default="",
            help=f"Header image URL (default: {DEFAULT_WELCOME_HEADER_IMAGE_URL}).",
        )
        parser.add_argument(
            "--skip-existing",
            action="store_true",
            help="Skip templates that already exist on the WABA.",
        )
        parser.add_argument(
            "--no-header",
            action="store_true",
            help="Create templates without IMAGE header (fallback if upload fails).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print payloads without calling Meta API.",
        )

    def handle(self, *args, **options):
        waba_id = (options["waba_id"] or waba_id_from_env()).strip()
        access_token = (options["access_token"] or access_token_from_env()).strip()
        app_id = (options["app_id"] or meta_app_id_from_env()).strip()
        header_image_url = (
            options["header_image_url"] or DEFAULT_WELCOME_HEADER_IMAGE_URL
        ).strip()
        try:
            languages = self._selected_languages(options["languages"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        if not options["dry_run"]:
            if not waba_id or not access_token:
                self.stderr.write(
                    self.style.ERROR(
                        "WHATSAPP_WABA_ID and WHATSAPP_ACCESS_TOKEN are required.\n"
                        "  export WHATSAPP_WABA_ID='...'\n"
                        "  export WHATSAPP_ACCESS_TOKEN='...'\n"
                        "  docker compose exec django python manage.py whatsapp_create_welcome_templates"
                    )
                )
                return
            if not options["no_header"] and not app_id:
                self.stderr.write(
                    self.style.ERROR(
                        "META_APP_ID is required for header image upload "
                        "(or pass --no-header)."
                    )
                )
                return

        header_handle: str | None = None
        if not options["no_header"]:
            if options["dry_run"]:
                header_handle = "upload:DRY_RUN_HEADER_HANDLE"
            else:
                try:
                    header_handle = upload_template_header_from_url(
                        app_id=app_id,
                        access_token=access_token,
                        image_url=header_image_url,
                    )
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Uploaded header image handle={header_handle[:24]}..."
                        )
                    )
                except MetaTemplateApiError as exc:
                    self.stderr.write(
                        self.style.ERROR(f"Header upload failed: {exc}")
                    )
                    return

        created = 0
        skipped = 0
        failed = 0

        for lang in languages:
            definition = WELCOME_TEMPLATE_DEFINITIONS[lang]
            payload = build_welcome_template_payload(
                definition,
                header_handle=header_handle,
            )

            if options["dry_run"]:
                self.stdout.write(
                    f"\n--- {definition.name} ({definition.language}) ---\n"
                    f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
                )
                continue

            if options["skip_existing"]:
                existing = find_message_template(
                    waba_id=waba_id,
                    access_token=access_token,
                    name=definition.name,
                    language=definition.language,
                )
                if existing is not None:
                    status = str(existing.get("status") or "").strip() or "UNKNOWN"
                    self.stdout.write(
                        self.style.WARNING(
                            f"Skip {definition.name} ({definition.language}) — "
                            f"already exists (status={status})."
                        )
                    )
                    skipped += 1
                    continue

            try:
                result = create_message_template(
                    waba_id=waba_id,
                    access_token=access_token,
                    payload=payload,
                )
            except MetaTemplateApiError as exc:
                self.stderr.write(
                    self.style.ERROR(
                        f"Failed {definition.name} ({definition.language}): {exc}"
                    )
                )
                failed += 1
                continue

            template_id = str(result.get("id") or result.get("h") or "").strip()
            status = str(result.get("status") or "PENDING").strip()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Created {definition.name} ({definition.language}) "
                    f"id={template_id or 'n/a'} status={status}"
                )
            )
            created += 1

        if options["dry_run"]:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Dry run complete for {len(languages)} template(s)."
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. created={created} skipped={skipped} failed={failed}"
            )
        )

    def _selected_languages(self, languages: list[str]) -> list[str]:
        if not languages:
            return list(WELCOME_TEMPLATE_DEFINITIONS.keys())

        selected: list[str] = []
        for raw in languages:
            lang = raw.strip().lower()
            if lang not in WELCOME_TEMPLATE_DEFINITIONS:
                valid = ", ".join(WELCOME_TEMPLATE_DEFINITIONS.keys())
                raise ValueError(f"Unknown language {raw!r}. Valid: {valid}")
            if lang not in selected:
                selected.append(lang)
        return selected
