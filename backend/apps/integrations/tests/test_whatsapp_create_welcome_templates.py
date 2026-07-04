from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from apps.integrations.whatsapp.meta_templates import (
    create_message_template,
    upload_template_header_handle,
)
from apps.integrations.whatsapp.welcome_template_definitions import (
    WELCOME_TEMPLATE_DEFINITIONS,
    build_welcome_template_payload,
)


class WelcomeTemplateDefinitionsTests(SimpleTestCase):
    def test_build_payload_includes_header_body_and_button(self):
        payload = build_welcome_template_payload(
            WELCOME_TEMPLATE_DEFINITIONS["hr"],
            header_handle="4::example",
        )
        self.assertEqual(payload["name"], "stay_welcome_hr")
        self.assertEqual(payload["language"], "hr")
        self.assertEqual(payload["category"], "UTILITY")
        self.assertEqual(len(payload["components"]), 3)
        self.assertEqual(payload["components"][0]["type"], "HEADER")
        self.assertEqual(payload["components"][1]["type"], "BODY")
        self.assertEqual(payload["components"][2]["type"], "BUTTONS")
        self.assertIn("Autocheck-in", payload["components"][1]["text"])


class MetaTemplateApiTests(SimpleTestCase):
    @patch("apps.integrations.whatsapp.meta_templates.httpx.post")
    def test_upload_template_header_handle(self, mock_post):
        session_response = MagicMock()
        session_response.status_code = 200
        session_response.json.return_value = {"id": "upload:session123"}

        upload_response = MagicMock()
        upload_response.status_code = 200
        upload_response.json.return_value = {"h": "4::header-handle"}

        mock_post.side_effect = [session_response, upload_response]

        handle = upload_template_header_handle(
            app_id="2246064206156468",
            access_token="token",
            file_bytes=b"png-bytes",
            mime_type="image/png",
            file_name="whatsapp-header.png",
        )
        self.assertEqual(handle, "4::header-handle")
        self.assertEqual(mock_post.call_count, 2)

    @patch("apps.integrations.whatsapp.meta_templates.httpx.post")
    def test_create_message_template(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "123", "status": "PENDING"}
        mock_post.return_value = mock_response

        result = create_message_template(
            waba_id="1227044268479415",
            access_token="token",
            payload={"name": "stay_welcome_hr"},
        )
        self.assertEqual(result["status"], "PENDING")
        self.assertIn("/1227044268479415/message_templates", mock_post.call_args.args[0])


class WhatsAppCreateWelcomeTemplatesCommandTests(SimpleTestCase):
    @patch(
        "apps.integrations.management.commands.whatsapp_create_welcome_templates.upload_template_header_from_url"
    )
    @patch(
        "apps.integrations.management.commands.whatsapp_create_welcome_templates.create_message_template"
    )
    @patch(
        "apps.integrations.management.commands.whatsapp_create_welcome_templates.find_message_template"
    )
    @patch.dict(
        "os.environ",
        {
            "WHATSAPP_WABA_ID": "1227044268479415",
            "WHATSAPP_ACCESS_TOKEN": "token",
            "META_APP_ID": "2246064206156468",
        },
    )
    def test_command_creates_templates(
        self,
        mock_find,
        mock_create,
        mock_upload,
    ):
        mock_upload.return_value = "4::header-handle"
        mock_find.return_value = None
        mock_create.return_value = {"id": "999", "status": "PENDING"}

        call_command(
            "whatsapp_create_welcome_templates",
            "--language",
            "hr",
            "--language",
            "en",
        )

        self.assertEqual(mock_create.call_count, 2)
        first_payload = mock_create.call_args_list[0].kwargs["payload"]
        self.assertEqual(first_payload["name"], "stay_welcome_hr")

    @patch.dict("os.environ", {}, clear=True)
    def test_command_requires_credentials_without_dry_run(self):
        from io import StringIO

        err = StringIO()
        call_command(
            "whatsapp_create_welcome_templates",
            "--language",
            "hr",
            stderr=err,
        )
        self.assertIn("WHATSAPP_WABA_ID", err.getvalue())

    def test_command_dry_run_does_not_require_credentials(self):
        call_command(
            "whatsapp_create_welcome_templates",
            "--dry-run",
            "--language",
            "hr",
        )

    def test_unknown_language_raises(self):
        with self.assertRaises(CommandError):
            call_command(
                "whatsapp_create_welcome_templates",
                "--dry-run",
                "--language",
                "xx",
            )
