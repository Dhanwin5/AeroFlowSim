"""Tests for core/plots.py and the in-memory CSV/PNG helpers in core/runner.py."""

import io

import numpy as np
import pytest

from core.mesh import Mesh1D, Mesh2D
from core.plots import MAX_PLOT_POINTS, field_figure, mesh_figure, residual_figure
from core.results import Field, Result
from core.runner import fields_csv_text, plot_fields


def test_mesh_figure_1d_shows_every_node():
    fig = mesh_figure(Mesh1D(x=np.linspace(0.0, 1.0, 11)))
    nodes = [t for t in fig.data if t.name == "nodes"][0]
    assert len(nodes.x) == 11
    assert "10 cells" in fig.layout.title.text


def test_mesh_figure_2d_draws_grid_lines():
    X, Y = np.meshgrid(np.linspace(0, 1, 4), np.linspace(0, 0.5, 3), indexing="ij")
    fig = mesh_figure(Mesh2D(x=X, y=Y))
    # 4 lines of constant i (3 points + gap) + 3 lines of constant j (4 points + gap)
    assert len(fig.data[0].x) == 4 * 4 + 3 * 5
    assert "6 cells" in fig.layout.title.text


def test_mesh_figure_rejects_unknown_mesh():
    with pytest.raises(TypeError):
        mesh_figure("not a mesh")


def test_residual_figure_is_log_and_thinned():
    n = 3 * MAX_PLOT_POINTS
    fig = residual_figure(np.arange(1, n + 1), np.logspace(0, -10, n), tol=1e-10)
    assert fig.layout.yaxis.type == "log"
    assert len(fig.data[0].x) <= MAX_PLOT_POINTS + 1
    assert fig.data[0].x[-1] == n  # last iteration is always kept


def test_field_figure_with_and_without_reference():
    mesh = Mesh1D(x=np.linspace(0.0, 1.0, 5))
    T = Field(values=np.full(5, 300.0), unit="K", label="Temperature")
    assert len(field_figure(mesh, T).data) == 1
    fig = field_figure(mesh, T, T)
    assert len(fig.data) == 2
    assert fig.layout.yaxis.title.text == "Temperature [K]"


def _result():
    mesh = Mesh1D(x=np.linspace(0.0, 1.0, 3))
    result = Result(fields={"T": Field(np.array([1.0, 2.0, 3.0]), "K", "Temperature"),
                            "p": Field(np.array([4.0, 5.0, 6.0]), "Pa", "Pressure")},
                    residuals=[1.0])
    reference = {"T": Field(np.array([1.0, 2.0, 3.0]), "K", "Temperature")}
    return mesh, result, reference


def test_fields_csv_text():
    mesh, result, reference = _result()
    lines = fields_csv_text(mesh, result, reference).splitlines()
    assert lines[0] == "x_m,T_K,p_Pa,T_exact_K"
    assert len(lines) == 4


def test_plot_fields_to_png_buffer_with_selected_field():
    mesh, result, reference = _result()
    buffer = io.BytesIO()
    case = type("Case", (), {"NAME": "test"})
    plot_fields(buffer, case, mesh, result, reference, keys=["p"])
    assert buffer.getvalue()[:8] == b"\x89PNG\r\n\x1a\n"


def test_cell_centred_fields_plot_and_csv_at_cell_centres():
    mesh = Mesh1D(x=np.linspace(0.0, 1.0, 5))   # 4 cells, centres 0.125 ... 0.875
    rho = Field(np.ones(4), "kg/m³", "Density")
    fig = field_figure(mesh, rho, rho)
    assert np.allclose(fig.data[0].x, mesh.xc)
    result = Result(fields={"rho": rho}, residuals=[1.0])
    lines = fields_csv_text(mesh, result, {"rho": rho}).splitlines()
    assert len(lines) == 5
    assert float(lines[1].split(",")[0]) == pytest.approx(0.125)
