"""Streamlit GUI (placeholder).

Start with:  streamlit run app.py
The real Setup / Mesh / Run / Results pages will be built in a later step.
"""

import streamlit as st

from core.discovery import find_cases

st.set_page_config(page_title="nozzle-cfd", layout="wide")
st.title("nozzle-cfd")

cases, problems = find_cases()
case_name = st.sidebar.selectbox("Case", list(cases), format_func=lambda n: cases[n].NAME)
for name, problem in problems.items():
    st.sidebar.warning(f"Case '{name}' is broken: {problem}")

if case_name:
    st.caption(cases[case_name].DESCRIPTION)

setup_tab, mesh_tab, run_tab, results_tab = st.tabs(["Setup", "Mesh", "Run", "Results"])
for tab in (setup_tab, mesh_tab, run_tab, results_tab):
    with tab:
        st.info("Coming soon.")
