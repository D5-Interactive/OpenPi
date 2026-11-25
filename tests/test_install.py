import pytest

from openpi.pi import install


def test_installed_version_reads_the_binary(tmp_path):
    fake = tmp_path / "pi"
    fake.write_text("#!/bin/sh\necho 1.6.1\n")
    fake.chmod(0o755)
    assert install.installed_version(str(fake)) == "1.6.1"


def test_installed_version_returns_none_for_a_missing_binary(tmp_path):
    assert install.installed_version(str(tmp_path / "does-not-exist")) is None


def test_ensure_pi_returns_an_existing_binary_without_touching_network(tmp_path, monkeypatch):
    fake = tmp_path / "pi"
    fake.write_text("#!/bin/sh\necho 9.9.9\n")
    fake.chmod(0o755)
    monkeypatch.setattr(install, "latest_version", lambda: None)  # no network in tests
    assert install.ensure_pi(update=True, binary=str(fake)) == str(fake)


@pytest.mark.live
def test_latest_version_comes_back_from_the_registry():
    version = install.latest_version()
    assert version and version.count(".") >= 1
