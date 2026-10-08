"""Deletion and addition must not escape an immutable-source audit."""
import subprocess

import pytest

import check_p3c_source as source


@pytest.fixture
def frozen_tree(tmp_path, monkeypatch):
    monkeypatch.setattr(source, "ROOT", tmp_path)
    models = tmp_path/"models"
    models.mkdir()
    (models/"robot.sdf").write_text("original physical model\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.email=fixture@example.invalid", "-c", "user.name=Fixture",
                    "commit", "-qm", "immutable fixture"], cwd=tmp_path, check=True)
    return models


def test_unchanged_physical_inventory_passes(frozen_tree):
    source.check_inventory(list(frozen_tree.iterdir()), ["models"], "HEAD")


@pytest.mark.parametrize("mutation", ["delete", "add"])
def test_physical_inventory_rejects_missing_or_new_sources(frozen_tree, mutation):
    if mutation == "delete":
        (frozen_tree/"robot.sdf").unlink()
    else:
        (frozen_tree/"extra.sdf").write_text("unexpected physical model\n")
    with pytest.raises(AssertionError):
        source.check_inventory(list(frozen_tree.iterdir()), ["models"], "HEAD")
