import asyncio
from unittest.mock import AsyncMock
from ingestion.src.main import RealTimePipelineRunner


def test_resolve_target_areas_primary_path():
    """Verify that primary path resolves mapped areas directly from client JSON."""
    async def _test():
        runner = RealTimePipelineRunner(dry_run=True)
        
        # Should resolve mapped areas directly from loaded JSON without hitting client.get_areas
        mock_client = AsyncMock()
        mock_client.get_areas = AsyncMock()

        areas = await runner.resolve_target_areas(client=mock_client)
        
        assert len(areas) > 0
        # In primary path, mock_client.get_areas must NOT be called for domain discovery
        mock_client.get_areas.assert_not_called()

    asyncio.run(_test())


def test_resolve_target_areas_filter_domain_id():
    """Verify filtering by domain ID."""
    async def _test():
        runner = RealTimePipelineRunner(dry_run=True)
        
        # Filter by BANK_FINANS
        areas = await runner.resolve_target_areas(domain_filter="BANK_FINANS")
        assert isinstance(areas, list)
        assert len(areas) > 0

    asyncio.run(_test())


def test_resolve_target_areas_fallback_path():
    """Verify fallback triggers when client JSON is not loaded and filters OUT_OF_SCOPE."""
    async def _test():
        runner = RealTimePipelineRunner(dry_run=True)
        
        # Force client mapping to appear not loaded
        runner.mapping_bundle.is_client_mapping_loaded = False
        runner.domain_plans = {}
        runner.mapping_bundle.out_of_scope = [{"rettsomrade": "Strafferett"}]
        runner.mapping_bundle.direct_mappings = [
            {"rettsomrade": "Finansielle tjenester", "domain_id": "BANK_FINANS"}
        ]

        mock_client = AsyncMock()
        mock_client.get_areas.return_value = (
            [
                {"rettsomrade": "Strafferett"},               # OUT_OF_SCOPE - must be dropped
                {"rettsomrade": "Finansielle tjenester"},       # Mapped - must be kept
                {"rettsomrade": "Ukjent Område"},              # Unmapped - must be dropped
            ],
            None,
            None,
        )

        areas = await runner.resolve_target_areas(client=mock_client)

        # Must have called fallback endpoint
        mock_client.get_areas.assert_called_once()
        # Must only contain the in-scope mapped area
        assert "Finansielle tjenester" in areas
        assert "Strafferett" not in areas
        assert "Ukjent Område" not in areas

    asyncio.run(_test())
