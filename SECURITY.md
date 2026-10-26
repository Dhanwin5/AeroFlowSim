# Security policy

AeroFlowSim is a desktop program: it makes no network connections, opens only local files and runs no code
from project files (results are read without pickle; custom field formulas are parsed with a whitelist, never
evaluated as Python).

**Reporting a vulnerability.** Please do not open a public issue. Write to the maintainer through the e-mail
address on the GitHub profile of the repository owner, with a description and, if possible, a file or project that
shows the problem. You will get an answer within two weeks. Supported version: the latest release.
