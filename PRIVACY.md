# AeroFlowSim privacy policy

Last updated: 9 November 2026. Applies to the AeroFlowSim program and to its Claude plugin and AI connector.

AeroFlowSim is free, open-source software (GPL-3.0-or-later) that runs on your own computer. Its author does not run
any server for it and does not receive, collect, store or sell any data from you.

## The program

* The desktop program makes **no network connections**, contains no web addresses, collects **no usage statistics**
  and sends nothing anywhere. This is checked by an automatic test on every change (`tests/test_gui_privacy.py`).
* Your projects, geometry, meshes and results stay in the folders you choose on your computer.

## The Claude plugin and AI connector (optional, used only if you add it)

| What | Where it goes |
|---|---|
| The connection between Claude and AeroFlowSim | Local: Claude starts the AeroFlowSim program on your computer and talks to it through its standard input and output. No network port, no internet connection made by AeroFlowSim, no statistics. |
| What Claude reads from AeroFlowSim (template descriptions, input values, result numbers, check messages, pictures, documentation snippets) | Into your conversation with Claude, like anything you type or share there. Anthropic's privacy policy applies to your conversations. Do not use the plugin for designs you may not share with your AI provider. |
| Project files, meshes and results | Stay on your computer, inside the workspace folder (default `Documents/AeroFlowSim Projects`). The connector cannot work outside that folder and never deletes or overwrites files. |
| Your AI account | Claude uses your own account and plan. AeroFlowSim never sees your credentials. |

## The optional built-in assistant

The program's own optional assistant (off by default) can use a model on your own computer, or, only if you turn
it on and enter your own key, an online model service of your choice; what you then send goes to that service under
its own privacy policy. Your key is kept in your operating system's keyring.

## Contact

Questions: open an issue at https://github.com/Dhanwin5/AeroFlowSim/issues .
