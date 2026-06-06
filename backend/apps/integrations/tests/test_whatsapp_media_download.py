from django.test import SimpleTestCase

from apps.integrations.whatsapp.media_download import rewrite_d360_media_download_url


class RewriteD360MediaDownloadUrlTests(SimpleTestCase):
    def test_rewrites_facebook_cdn_host(self):
        raw = (
            "https://lookaside.fbsbx.com\\/whatsapp_business\\/attachments\\/"
            "?mid=1892054061371916&source=getMedia&ext=1757082791&hash=abc"
        )
        result = rewrite_d360_media_download_url(
            raw,
            api_base_url="https://waba-v2.360dialog.io",
        )
        self.assertEqual(
            result,
            "https://waba-v2.360dialog.io/whatsapp_business/attachments/"
            "?mid=1892054061371916&source=getMedia&ext=1757082791&hash=abc",
        )
