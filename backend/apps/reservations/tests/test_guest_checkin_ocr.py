from django.test import TestCase

from apps.reservations.guest_checkin_ocr import build_field_confidence, person_to_guest_preview


class GuestCheckInOcrTests(TestCase):
    def test_build_field_confidence_marks_empty_as_low(self):
        person = {"given_names": "Ana", "surnames": ""}
        ocr_result = {"_telemetry": {"persons": [{"person_index": 0, "reasons": []}]}}
        confidence = build_field_confidence(
            person=person,
            ocr_result=ocr_result,
            match={"confidence": "high"},
        )
        self.assertEqual(confidence["first_name"], "high")
        self.assertEqual(confidence["last_name"], "low")

    def test_person_to_guest_preview_maps_document_type(self):
        preview = person_to_guest_preview(
            {
                "given_names": "John",
                "surnames": "Doe",
                "document_type": "passport",
                "nationality": "DEU",
                "sex": "M",
            }
        )
        self.assertEqual(preview["document_type"], "passport")
        self.assertEqual(preview["nationality"], "DE")
        self.assertEqual(preview["sex"], "male")
