from django.test import TestCase

from apps.integrations.channex.config import ChannexRuntimeConfig
from apps.integrations.channex.mapping import UZORITA_STAGING_ROOM_TYPES


class ChannexMappingTests(TestCase):
    def test_uzorita_has_four_physical_rooms(self):
        self.assertEqual(len(UZORITA_STAGING_ROOM_TYPES), 4)
        codes = {row["unit_code"] for row in UZORITA_STAGING_ROOM_TYPES}
        self.assertEqual(codes, {"R1", "R2", "D1", "R3"})

    def test_runtime_config_lookup_by_unit_code(self):
        config = ChannexRuntimeConfig.from_integration_dict(
            {
                "environment": "staging",
                "property_id": "prop-uuid",
                "api_key": "key",
                "room_types": list(UZORITA_STAGING_ROOM_TYPES),
            }
        )
        self.assertEqual(
            config.room_type_id_for_unit_code("R1"),
            "e8fc8060-3df5-4e49-bee9-32903786b4ee",
        )
        self.assertEqual(
            config.unit_code_for_room_type_id("6058e4da-0ed4-48a1-a877-fec38685589a"),
            "R3",
        )
