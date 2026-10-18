import asyncio

from app import temporal_client
from app.config import Settings


def test_disabled_temporal_does_not_connect(monkeypatch) -> None:
    connect_called = False

    async def fail_if_called(*args, **kwargs):
        nonlocal connect_called
        connect_called = True
        raise AssertionError("Temporal must not connect when disabled")

    monkeypatch.setattr(temporal_client.Client, "connect", fail_if_called)

    client = asyncio.run(
        temporal_client.create_temporal_client(Settings(temporal_enabled=False))
    )

    assert client is None
    assert connect_called is False


def test_enabled_temporal_connects_with_configured_address_and_namespace(
    monkeypatch,
) -> None:
    calls = []
    expected_client = object()

    async def fake_connect(address, *, namespace):
        calls.append((address, namespace))
        return expected_client

    monkeypatch.setattr(temporal_client.Client, "connect", fake_connect)

    client = asyncio.run(
        temporal_client.create_temporal_client(
            Settings(
                temporal_enabled=True,
                temporal_address="temporal.example:7233",
                temporal_namespace="rainguard",
            )
        )
    )

    assert client is expected_client
    assert calls == [("temporal.example:7233", "rainguard")]
