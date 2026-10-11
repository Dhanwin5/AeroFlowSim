"""The case "contract": what every cases/<name>/case.py must provide.

A case.py file must define:

    NAME          str   short human-readable name, e.g. "1D heat conduction (demo)"
    DESCRIPTION   str   one or two sentences describing the case

    parameters()                  -> list[Parameter]
        The inputs of the case (see core/parameters.py).

    build_mesh(params)            -> Mesh1D
        params is a dict {name: value}. Returns the mesh (see core/mesh.py).

    run(params, mesh, progress)   -> Result
        Solves the problem. While iterating it calls progress(iteration, residual)
        so the GUI or the command line can show how the solution is converging.
        Returns a Result (see core/results.py).

    reference(params, mesh)       -> dict[str, Field] or None      (optional)
        Theory or exact solution on the same mesh. Keys should match the keys of
        Result.fields so the two can be compared and plotted together.

A ready-to-copy skeleton lives in cases/_template/.
"""

# Names every case must define, and which of them must be functions.
REQUIRED_TEXT = ["NAME", "DESCRIPTION"]
REQUIRED_FUNCTIONS = ["parameters", "build_mesh", "run"]
OPTIONAL_FUNCTIONS = ["reference"]


def check_case(module) -> list[str]:
    """Return a list of problems with a loaded case module (empty list = valid case)."""
    problems = []
    for name in REQUIRED_TEXT:
        if not isinstance(getattr(module, name, None), str):
            problems.append(f"missing text constant {name}")
    for name in REQUIRED_FUNCTIONS:
        if not callable(getattr(module, name, None)):
            problems.append(f"missing function {name}()")
    for name in OPTIONAL_FUNCTIONS:
        if hasattr(module, name) and not callable(getattr(module, name)):
            problems.append(f"{name} exists but is not a function")
    return problems


def get_reference(module, params, mesh):
    """Call the case's reference() if it has one; otherwise return None."""
    if hasattr(module, "reference"):
        return module.reference(params, mesh)
    return None
