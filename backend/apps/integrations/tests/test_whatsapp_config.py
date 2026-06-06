from unittest.mock import patch

from django.test import SimpleTestCase

from apps.integrations.whatsapp.config import (
    is_360dialog_provider,
    provider_from_env,
    webhook_verify_signature_from_env,
)
from apps.integrations.whatsapp.runtime_config import WhatsAppRuntimeConfig


class WhatsAppConfigTests(SimpleTestCase):
    @patch.dict("os.environ", {"WHATSAPP_PROVIDER": "360dialog"}, clear=False)
    def test_provider_from_env(self):
        self.assertEqual(provider_from_env(), "360dialog")
        self.assertTrue(is_360dialog_provider("360dialog"))

    @patch.dict(
        "os.environ",
        {"WHATSAPP_PROVIDER": "360dialog", "WHATSAPP_WEBHOOK_VERIFY_SIGNATURE": ""},
        clear=False,
    )
    def test_webhook_signature_disabled_for_360dialog_by_default(self):
        self.assertFalse(webhook_verify_signature_from_env())

    @patch.dict(
        "os.environ",
        {"D360_API_KEY": "from-env"},
        clear=False,
    )
    def test_runtime_config_uses_env_d360_key(self):
        runtime = WhatsAppRuntimeConfig.from_integration_dict({"provider": "360dialog"})
        self.assertEqual(runtime.access_token, "from-env")
        self.assertTrue(runtime.send_credentials_ok())
