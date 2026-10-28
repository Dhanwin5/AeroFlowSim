# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The command line side:  python -m aeroflowsim assist "<description>" --case <project or case> [--dry-run | --apply]

Imported by aeroflowsim/cli.py only when the command is used. Typing the command is the opt-in for the
"rules" provider (it needs no model and contacts nothing); "local" needs --provider local and --model;
"online" needs --provider online, --model, --url and --allow-online. The online key comes from the
operating system's keyring (store it with:  python -m aeroflowsim assist-key set).
"""

from aeroflowsim.assistant.config import AssistantSettings, make_provider
from aeroflowsim.assistant.context import SchemaContext
from aeroflowsim.assistant.proposal import AssistantError
from aeroflowsim.assistant.review import review_proposals


def format_value(value, unit):
    if isinstance(value, float):
        value = f"{value:.6g}"
    return f"{value} {unit}".strip() if unit not in ("", "-") else str(value)


def format_review(review, notes=()) -> str:
    """The review table as text: field, old, new, reason (values in the inputs' own, SI, units)."""
    lines = []
    if review.rows:
        width = max(len(r.name) for r in review.rows)
        lines.append(f"{'field':<{width}}  {'old':>14}  {'new':>14}  reason")
        for r in review.rows:
            lines.append(f"{r.name:<{width}}  {format_value(r.old, r.unit):>14}  {format_value(r.new, r.unit):>14}  {r.reason}")
    else:
        lines.append("No input would change.")
    for r in review.rejected:
        lines.append(f"REJECTED {r.proposal.field}: {r.message}")
    for name in review.unchanged:
        lines.append(f"unchanged {name}: already has the proposed value")
    lines += [f"note: {n}" for n in notes]
    return "\n".join(lines)


def command_assist(args) -> int:
    from aeroflowsim.discovery import load_case
    from aeroflowsim.parameters import defaults
    from aeroflowsim.project import Project, is_project
    if args.apply and args.dry_run:
        print("Error: use either --dry-run or --apply, not both.")
        return 1
    try:
        project = Project.open(args.case) if is_project(args.case) else None
        case = project.case if project else load_case(args.case)
        if args.apply and project is None:
            print("Error: --apply writes into a project (*.afsproj). A template is read-only: make a project in the GUI, "
                  "or use the --set line printed below with 'run'.")
            return 1
        values = dict(project.values) if project else defaults(case.parameters())
        settings = AssistantSettings(enabled=True, provider=args.provider, local_host=args.host, local_port=args.port,
                                     local_model=args.model or "", online_opt_in=args.allow_online,
                                     online_url=args.url or "", online_model=args.model or "")
        provider = make_provider(settings)
        context = SchemaContext(case.parameters(), values)
        proposals = provider.propose(args.description, context)
        review = review_proposals(context, proposals, from_model=provider.from_model, text=args.description)
    except (AssistantError, ValueError, OSError) as error:
        print(f"Error: {error}")
        return 1
    print(f"Assistant: {provider.label} ({provider.status_text()}). Nothing is applied without --apply.")
    print(format_review(review, provider.notes))
    if review.rows and project is None:
        print("Same values for 'run':  " + " ".join(f'--set "{r.name}={r.new}"' for r in review.rows))
    if args.apply:
        for row in review.rows:
            project.set_value(row.name, row.new)
        if review.rows:
            project.save()
        print(f"Applied {len(review.rows)} value(s) to {project.folder}." if review.rows else "Nothing to apply.")
    return 0


def command_assist_key(args) -> int:
    import getpass

    from aeroflowsim.assistant import keystore
    try:
        if args.action == "set":
            keystore.set_key(getpass.getpass("Key for the online provider (not shown, stored in the OS keyring): "))
            print("Key stored in the operating system's keyring.")
        else:
            keystore.delete_key()
            print("Key removed from the operating system's keyring.")
    except AssistantError as error:
        print(f"Error: {error}")
        return 1
    return 0
