"""Tests for core/settings.py (save / load case inputs as YAML) and the mesh additions."""

import numpy as np
import pytest

from core.mesh import Mesh1D, Mesh2D
from core.parameters import Parameter, defaults
from core.settings import clean_file_name, list_settings, load_settings, save_settings

PARAMS = [
    Parameter("L", "Length", "m", 1.0, 0.1, 10.0),
    Parameter("n", "Nodes", "-", 11, 3, 101),
]


def test_save_list_load_round_trip(tmp_path):
    values = {"L": 2.5, "n": 21}
    path = save_settings("mycase", "my run", PARAMS, values, cases_dir=tmp_path)
    assert path == tmp_path / "mycase" / "settings" / "my_run.yaml"
    assert list_settings("mycase", cases_dir=tmp_path) == ["my_run"]
    loaded = load_settings("mycase", "my_run", PARAMS, cases_dir=tmp_path)
    assert loaded == values
    assert isinstance(loaded["n"], int)


def test_list_settings_of_case_without_folder_is_empty(tmp_path):
    assert list_settings("nothing_here", cases_dir=tmp_path) == []


def test_save_rejects_out_of_range_value(tmp_path):
    with pytest.raises(ValueError, match="outside the allowed range"):
        save_settings("mycase", "bad", PARAMS, {"L": 99.0, "n": 11}, cases_dir=tmp_path)


def test_load_fills_missing_parameter_with_default(tmp_path):
    save_settings("mycase", "old", PARAMS[:1], {"L": 3.0}, cases_dir=tmp_path)
    loaded = load_settings("mycase", "old", PARAMS, cases_dir=tmp_path)
    assert loaded == {"L": 3.0, "n": defaults(PARAMS)["n"]}


def test_load_rejects_file_of_other_case(tmp_path):
    path = save_settings("case_a", "s", PARAMS, defaults(PARAMS), cases_dir=tmp_path)
    other = tmp_path / "case_b" / "settings"
    other.mkdir(parents=True)
    (other / "s.yaml").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(ValueError, match="belongs to case"):
        load_settings("case_b", "s", PARAMS, cases_dir=tmp_path)


def test_clean_file_name():
    assert clean_file_name(" run 1.yaml ") == "run_1"
    with pytest.raises(ValueError):
        clean_file_name("  ")


def test_mesh_cell_counts():
    assert Mesh1D(x=np.linspace(0.0, 1.0, 5)).n_cells == 4
    X, Y = np.meshgrid(np.linspace(0, 1, 4), np.linspace(0, 1, 3), indexing="ij")
    mesh = Mesh2D(x=X, y=Y)
    assert mesh.n_nodes == 12
    assert mesh.n_cells == 6
