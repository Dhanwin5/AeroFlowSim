# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for aeroflowsim/schema.py (schema.toml reader) and the new parameter types and checks."""

import tomllib

import pytest

from aeroflowsim.discovery import find_cases
from aeroflowsim.parameters import Parameter, check_values, parse_value, validate
from aeroflowsim.schema import parse_schema

CASE = '[case]\nname = "Test"\ndescription = "A test case."\nsteady = false\n'


def schema_from(text):
    return parse_schema(tomllib.loads(CASE + text))


def test_all_input_types_are_read():
    s = schema_from('''
[[input]]
key = "L"
label = "Length"
unit = "m"
type = "float"
default = 1          # an integer in TOML, but a float input keeps float values
min = 0.1
max = 10.0
group = "Geometry"
help = "Rod length."

[[input]]
key = "n"
label = "Cells"
unit = "-"
type = "int"
default = 10
min = 2
max = 100

[[input]]
key = "flag"
label = "Second order"
type = "bool"
default = true

[[input]]
key = "src"
label = "Source"
type = "choice"
options = ["A", "B"]
default = "A"

[[input]]
key = "csv"
label = "Profile"
type = "file"
default = "x.csv"
show_if = { src = "B" }
''')
    assert (s.title, s.description, s.steady) == ("Test", "A test case.", False)
    L, n, flag, src, csv = s.inputs
    assert L.type == "float" and L.default == 1.0 and isinstance(L.default, float) and L.group == "Geometry"
    assert n.is_integer and n.default == 10
    assert flag.type == "bool" and flag.default is True
    assert src.options == ("A", "B")
    assert csv.show_if == ("src", "B")


@pytest.mark.parametrize("text, message", [
    ('[[input]]\nkey = "a"\nlabel = "A"\ntype = "float"\ndefault = 1.0\n', "needs 'unit'"),
    ('[[input]]\nkey = "a"\nlabel = "A"\ntype = "complex"\ndefault = 1.0\n', "not one of"),
    ('[[input]]\nkey = "a"\nlabel = "A"\nunit = "m"\ntype = "float"\ndefault = 5.0\nmin = 0.0\nmax = 1.0\n',
     "default is not allowed"),
    ('[[input]]\nkey = "a"\nlabel = "A"\ntype = "choice"\ndefault = "x"\n', "options"),
    ('[[input]]\nkey = "a"\nlabel = "A"\ntype = "bool"\ndefault = true\ncolour = "red"\n', "unknown field"),
    ('[[input]]\nlabel = "A"\ntype = "bool"\ndefault = true\n', "missing field 'key'"),
    ('[[input]]\nkey = "a"\nlabel = "A"\ntype = "bool"\ndefault = true\nshow_if = { b = 1 }\n', "unknown input"),
    ('[[input]]\nkey = "a"\nlabel = "A"\ntype = "bool"\ndefault = true\n'
     '[[input]]\nkey = "a"\nlabel = "B"\ntype = "bool"\ndefault = false\n', "used twice"),
])
def test_bad_schema_gives_clear_message(text, message):
    with pytest.raises(ValueError, match=message):
        schema_from(text)


def test_every_real_case_has_a_valid_schema_with_groups_and_help():
    cases, problems = find_cases()
    assert problems == {}
    assert {"demo_heat1d", "sod_shock_tube", "quasi1d_nozzle", "nozzle_axi"} <= set(cases)
    for case in cases.values():
        for p in case.parameters():
            assert p.group and p.help, f"{case.name}: input {p.name} needs a group and a help text"


def test_bool_parameter_and_check_values_collects_every_problem():
    params = [
        Parameter("L", "Length", "m", 1.0, 0.1, 10.0),
        Parameter("n", "Nodes", "-", 11, 3, 101),
        Parameter("flag", "Flag", "", True),
    ]
    assert params[2].type == "bool"
    assert validate(params, {"L": 1.0, "n": 5, "flag": False})["flag"] is False
    problems = check_values(params, {"L": 50.0, "n": 2.5, "flag": "maybe"})
    assert set(problems) == {"L", "n", "flag"}
    assert "outside the allowed range" in problems["L"]
    assert "whole number" in problems["n"]
    assert check_values(params, {"L": 1.0, "n": 5, "flag": True}) == {}
    assert parse_value(params[2], "yes") is True and parse_value(params[2], "False") is False


def test_options_that_need_a_missing_package_say_how_to_install_it(monkeypatch):
    s = schema_from('''
[[input]]
key = "mesh_type"
label = "Mesh type"
type = "choice"
default = "Structured"
options = ["Structured", "Triangles (Gmsh)"]
requires = { "Triangles (Gmsh)" = "gmsh" }
''')
    p = s.inputs[0]
    assert p.requires == {"Triangles (Gmsh)": "gmsh"}
    import aeroflowsim.parameters as parameters
    monkeypatch.setattr(parameters, "module_available", lambda name: False)
    problems = check_values([p], {"mesh_type": "Triangles (Gmsh)"})
    assert 'pip install -e ".[mesh]"' in problems["mesh_type"]
    assert check_values([p], {"mesh_type": "Structured"}) == {}
    with pytest.raises(ValueError, match="requires"):
        schema_from('[[input]]\nkey = "a"\nlabel = "A"\ntype = "choice"\ndefault = "x"\noptions = ["x"]\n'
                    'requires = { "y" = "gmsh" }\n')


def test_text_input_with_pattern_and_file_types():
    s = schema_from('''
[[input]]
key = "digits"
label = "Digits"
type = "text"
default = "0012"
pattern = "[0-9]{4}"

[[input]]
key = "f"
label = "File"
type = "file"
default = "x.dat"
file_types = ["dat", "csv"]
''')
    digits, f = s.inputs
    assert validate(s.inputs, {"digits": " 2412 ", "f": "a.dat"})["digits"] == "2412"
    assert "not allowed" in check_values([digits], {"digits": "24a"})["digits"]
    assert f.file_types == ("dat", "csv")


def test_case_level_requires_and_shape_library_flags():
    s = parse_schema(tomllib.loads(CASE + 'requires = ["gmsh"]\nshape_library = true\n'))
    assert s.requires == ["gmsh"] and s.shape_library
    assert not schema_from("").shape_library and schema_from("").requires == []
