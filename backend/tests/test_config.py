from pathlib import Path

from app import config


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
