# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""The ONLY place in AeroFlowSim with network code (tests/test_assistant.py checks that).

Imported by local.py and online.py, i.e. only after the user chose a local or an online provider and
pressed Propose. One function: send a JSON request, read a JSON answer. No redirects are followed
(a server cannot send the request somewhere else), the answer size is limited, and errors become
AssistantError messages the user can read.
"""

import json

from aeroflowsim.assistant.proposal import AssistantError

MAX_ANSWER_BYTES = 2_000_000
TIMEOUT_S = 120


def post_json(url: str, payload: dict, headers: dict | None = None, *, use_proxy: bool = True) -> dict:
    """POST `payload` as JSON to `url`; returns the decoded JSON answer. Raises AssistantError."""
    import urllib.error
    import urllib.request

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None

    handlers = [NoRedirect()] + ([] if use_proxy else [urllib.request.ProxyHandler({})])
    opener = urllib.request.build_opener(*handlers)
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with opener.open(request, timeout=TIMEOUT_S) as answer:
            body = answer.read(MAX_ANSWER_BYTES + 1)
    except urllib.error.HTTPError as error:
        raise AssistantError(f"The server answered with an error (HTTP {error.code}).") from None
    except (urllib.error.URLError, OSError, ValueError) as error:
        reason = getattr(error, "reason", error)
        raise AssistantError(f"Could not reach the server ({reason}).") from None
    if len(body) > MAX_ANSWER_BYTES:
        raise AssistantError("The server's answer was far too long; it was discarded.")
    try:
        return json.loads(body.decode("utf-8"))
    except ValueError:
        raise AssistantError("The server's answer was not JSON; it was discarded.") from None
