from temporalio.client import Client

from app.config import Settings


async def create_temporal_client(settings: Settings) -> Client | None:
    """Create a Temporal client when integration is explicitly enabled."""
    if not settings.temporal_enabled:
        return None
    return await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
    )
