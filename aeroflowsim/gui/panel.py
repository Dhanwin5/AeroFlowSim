# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The input panel of the Setup tab, built automatically from a case's schema.toml.

A case author writes no GUI code: this module looks at each input's type and draws the matching
Streamlit widget, under its group heading, with the unit in the label and the help text and
allowed range in the tooltip. Every value is checked (aeroflowsim.parameters.check_values) and a
red message appears under any box whose value is not allowed.

The values typed by the user live in Streamlit's st.session_state under the key "<case>:<input>",
e.g. "demo_heat1d:L", so they survive the page re-runs (see app.py for how Streamlit works).
"""

import math
from pathlib import Path

import streamlit as st

from aeroflowsim.parameters import check_values, defaults, install_hint, is_shown, module_available

NO_GROUP = "Inputs"   # heading for inputs without a group in schema.toml


def widget_key(case_name, param_name):
    """Session-state key of one input box, e.g. 'demo_heat1d:L'."""
    return f"{case_name}:{param_name}"


def float_step(p):
    """Step for the +/- buttons of a float input: about 1/10 of the default's order of magnitude."""
    size = abs(p.default) if p.default != 0 else (p.max - p.min) / 10.0
    if size <= 0.0:
        return 1.0
    return 10.0 ** (math.floor(math.log10(size)) - 1)


def init_inputs(case):
    """First visit of a case: fill its input boxes with the default values."""
    for name, value in defaults(case.parameters()).items():
        st.session_state.setdefault(widget_key(case.name, name), value)


def current_values(case):
    """The values currently in the input boxes: {key: value}."""
    return {p.name: st.session_state[widget_key(case.name, p.name)] for p in case.parameters()}


def set_inputs(case, values):
    """Put values into the input boxes (only allowed inside a button callback)."""
    for name, value in values.items():
        st.session_state[widget_key(case.name, name)] = value


def _on_upload(case_name, param_name, uploads_dir, project_dir):
    """Save an uploaded file to uploads/<case>/ and put its path into the file input box."""
    uploaded = st.session_state.get(f"upload:{case_name}:{param_name}")
    if uploaded is None:
        return
    folder = Path(uploads_dir) / case_name
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / Path(uploaded.name).name   # keep only the file name, never a folder part
    path.write_bytes(uploaded.getvalue())
    st.session_state[widget_key(case_name, param_name)] = path.relative_to(project_dir).as_posix()


def input_widget(case, p, uploads_dir, project_dir):
    """One input box for parameter p, chosen by its type (float, int, bool, choice or file)."""
    key = widget_key(case.name, p.name)
    if p.type == "choice":
        missing = {option: package for option, package in p.requires.items() if not module_available(package)}
        st.selectbox(p.label, p.options, key=key, help=p.help or None,
                     filter_mode=None,   # pick from the list only: no text cursor, no typing
                     format_func=lambda o: f"{o}  (not installed)" if o in missing else o)
        for option, package in missing.items():
            st.caption(f"'{option}' needs {package}: install it with `{install_hint(package)}`.")
    elif p.type == "text":
        st.text_input(p.label, key=key, help=p.help or None)
    elif p.type == "bool":
        st.checkbox(p.label, key=key, help=p.help or None)
    elif p.type == "file":
        st.text_input(f"{p.label} (path)", key=key,
                      help=f"{p.help}  \nA path relative to the project folder, or upload a file below.")
        st.file_uploader(f"Upload {p.label.lower()}", type=list(p.file_types), key=f"upload:{case.name}:{p.name}",
                         on_change=_on_upload, args=(case.name, p.name, uploads_dir, project_dir))
    else:
        label = f"{p.label} [{p.unit}]"
        help_text = f"{p.help}  \nAllowed range: {p.min:g} to {p.max:g} {p.unit}."
        if p.is_integer:
            st.number_input(label, min_value=int(p.min), max_value=int(p.max), step=1,
                            key=key, help=help_text)
        else:
            st.number_input(label, min_value=float(p.min), max_value=float(p.max),
                            step=float_step(p), format="%g", key=key, help=help_text)


def groups_in_order(param_list):
    """{group heading: [parameters]} in the order the groups first appear in schema.toml."""
    groups = {}
    for p in param_list:
        groups.setdefault(p.group or NO_GROUP, []).append(p)
    return groups


def input_panel(case, uploads_dir, project_dir):
    """Draw every (shown) input of the case, grouped, with a message under each bad value.

    Returns the problems found {key: message} (empty dict = all values are fine).
    """
    values = current_values(case)
    problems = check_values(case.parameters(), values)
    for group, params in groups_in_order(case.parameters()).items():
        shown = [p for p in params if is_shown(p, values, case.parameters())]   # e.g. hide the CSV path for "parametric"
        if not shown:
            continue
        st.markdown(f"**{group}**")
        columns = st.columns(2)
        for i, p in enumerate(shown):
            with columns[i % 2]:
                input_widget(case, p, uploads_dir, project_dir)
                if p.name in problems:
                    st.error(problems[p.name])
    return problems
