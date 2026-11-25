from openpi import config


def test_home_dir_respects_OPENPI_HOME(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENPI_HOME", str(tmp_path / "custom"))
    assert config.home_dir() == tmp_path / "custom"


def test_ensure_home_creates_layout(tmp_path):
    config.ensure_home(tmp_path)
    assert (tmp_path / "extensions").is_dir()
    assert (tmp_path / "skills").is_dir()


def test_ensure_home_migrates_legacy_files(monkeypatch, tmp_path):
    home = tmp_path / "home"
    legacy = tmp_path / "legacy" / "openpi"
    legacy.mkdir(parents=True)
    (legacy / "settings.json").write_text("{}")
    (legacy / "pairings.json").write_text("[]")
    monkeypatch.setattr(config, "home_dir", lambda: home)
    monkeypatch.setattr(config, "legacy_dir", lambda: legacy)
    monkeypatch.delenv("OPENPI_HOME", raising=False)

    config.ensure_home()

    assert (home / "settings.json").exists()
    assert (home / "pairings.json").exists()
    assert (home / "extensions").is_dir() and (home / "skills").is_dir()


def test_settings_save_loads_into_the_home_dir(tmp_path):
    settings = config.Settings(projects=["/a", "/b"], last_project="/a")
    config.save(settings, tmp_path)
    loaded = config.load(tmp_path)
    assert loaded.projects == ["/a", "/b"]
    assert loaded.last_project == "/a"
