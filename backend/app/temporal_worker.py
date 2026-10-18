from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

from temporalio.worker import Worker

from app.config import Settings, get_settings
from app.database import MongoConnection
from app.temporal_activities import MaintenanceTaskActivities
from app.temporal_client import create_temporal_client
from app.temporal_workflows import MaintenanceTaskWorkflow

TASK_QUEUE = "rainguard-maintenance"


class TemporalDisabledError(RuntimeError):
    """Raised when the worker is started without enabling Temporal."""


async def run_worker(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    if not settings.temporal_enabled:
        raise TemporalDisabledError(
            "Temporal worker is disabled; set TEMPORAL_ENABLED=true to start it"
        )

    client = await create_temporal_client(settings)
    if client is None:
        raise TemporalDisabledError(
            "Temporal worker did not receive an enabled Temporal client"
        )

    connection = MongoConnection(settings)
    connection.connect()
    activity_executor = ThreadPoolExecutor(
        max_workers=4,
        thread_name_prefix="rainguard-temporal-activity",
    )
    try:
        activities = MaintenanceTaskActivities(connection.database)
        worker = Worker(
            client,
            task_queue=TASK_QUEUE,
            workflows=[MaintenanceTaskWorkflow],
            activities=[activities.create_maintenance_task],
            activity_executor=activity_executor,
        )
        await worker.run()
    finally:
        activity_executor.shutdown(wait=True)
        connection.close()


if __name__ == "__main__":
    asyncio.run(run_worker())
