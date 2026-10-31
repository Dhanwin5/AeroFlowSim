# AI assistant stage - progress ledger (AI assistant plugin)

Updated after each part so a new session can continue. Model: Sonnet. Rule: the assistant only fills schema inputs,
every proposal is checked against the schema, nothing is applied without the user ticking it, off by default.

| Part | What | Status |
|---|---|---|
| 1 | Provider interface `aeroflowsim/assistant/` (Rules, Local model, Online with own key), strict JSON | done |
| 2 | Schema context (prompt built from schema.toml; only the user's text + field definitions go to a model) | done |
| 3 | GUI: Assistant panel in the Setup step, Tools > Assistant settings, status line, light/dark screenshots | done (`docs/screenshots/assistant/`, made by `tools/assistant_screenshots.py`) |
| 4 | CLI: `python -m aeroflowsim assist "<text>" --case <project or case> [--dry-run] [--apply]`, `assist-key` | done |
| 5 | Tests: `tests/test_assistant.py` (no Qt), `tests/gui/test_assistant_gui.py` (fake provider) | done |
| 6 | Docs: user guide section + privacy table, theory manual section 15, CLAUDE.md layout + rule 12, gap register | done |

## Decisions
- Network code lives ONLY in `aeroflowsim/assistant/net.py` (imported lazily by the local / online providers). The GUI
  files stay free of network code and web addresses (`tests/test_gui_privacy.py` unchanged); the local server is typed
  as host + port in the GUI.
- `aeroflowsim/assistant/__init__.py` imports nothing; the GUI imports the package only after the user turned the
  assistant on (the flag is one QSettings value, `assistant/enabled`). Tested in a fresh process, with every socket
  made an error.
- The online provider speaks the common "chat completions" JSON format to an https address the user types
  (no address is built in) with a key from the OS keyring (optional package `keyring`, extra `[assistant]`).
- A model's numbers must appear in the user's text (no physics numbers from memory); gas-property fields are refused
  for a model. The rules provider's numbers are the user's own words by construction.
- `--case` of the CLI takes a project (*.afsproj) or a template; `--apply` needs a project (a template is read-only).
- Rule 12 of CLAUDE.md got an explicit exception for the assistant (the user asked for the opt-in online provider).

## Findings / open points
- Not tried against a real local model or online service (no server, no `keyring`, no key here): see the gap register.
- Rules provider limits (documented): shapes named in full, no number words, no radius -> diameter.
- The settings dialog and the panel were checked in light and dark; the settings dialog itself has no screenshot.
