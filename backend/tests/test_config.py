from pathlib import Path

from app import config


def test_temporal_configuration_is_disabled_by_default(monkeypatch) -> None:
    for name in ("TEMPORAL_ADDRESS", "TEMPORAL_NAMESPACE", "TEMPORAL_ENABLED"):
        monkeypatch.delenv(name, raising=False)

    settings = config.get_settings()

    assert settings.temporal_address == "127.0.0.1:7233"
    assert settings.temporal_namespace == "default"
    assert settings.temporal_enabled is False


def test_temporal_configuration_can_be_enabled(monkeypatch) -> None:
    monkeypatch.setenv("TEMPORAL_ADDRESS", "temporal.example:7233")
    monkeypatch.setenv("TEMPORAL_NAMESPACE", "rainguard")
    monkeypatch.setenv("TEMPORAL_ENABLED", "true")

    settings = config.get_settings()

    assert settings.temporal_address == "temporal.example:7233"
    assert settings.temporal_namespace == "rainguard"
    assert settings.temporal_enabled is True


def test_environment_file_path_is_independent_of_working_directory(
    monkeypatch, tmp_path
) -> None:
    loaded_paths: list[Path] = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        config,
        "load_dotenv",
        lambda *, dotenv_path: loaded_paths.append(Path(dotenv_path)),
    )

    config._load_environment()

    assert loaded_paths == [Path(config.__file__).resolve().parents[1] / ".env"]
