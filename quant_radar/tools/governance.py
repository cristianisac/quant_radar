"""Agent-governance helpers.

When the in-app Claude session receives a request that can't be
fulfilled with ``quant_radar.tools.*`` + the kinds/sources documented
in ``TOOLS.md``, it must NOT freelance (WebFetch, ad-hoc scraping,
shell shortcuts) to fabricate a card. Instead it surfaces the user
this structured menu and waits for the user's pick.

This module provides the structured payload. The SKILL.md
"Coverage discipline" section instructs the agent to call
``tools.request_user_decision(...)`` whenever it detects a coverage
gap. The agent then reads back the menu to the user, takes their
answer, and either:

- A · exit the current request
- B · queue the integration work (close app, add tool/source, restart)
- C · solve the request via base tools (WebFetch, Bash, etc.) and
      print the result in chat — explicitly NOT as a card

The "is this supported?" check is a judgment call the agent makes.
Adapters fail noisily on unknown sources/kinds, so the cheapest
detection is *try it; on failure, ask*. The SKILL.md guidance is to
**also** ask BEFORE trying when the request involves an obvious gap
(e.g. user asks for an asset class we don't list in TOOLS.md).
"""

from __future__ import annotations

from typing import Any, Literal

# Strings are agent-readable — the agent surfaces them verbatim to the user.
_DEFAULT_OPTIONS: list[dict[str, str]] = [
    {
        "key": "A",
        "label": "Exit this request",
        "description": (
            "Abandon the current request. The app stays running; "
            "nothing new is created."
        ),
    },
    {
        "key": "B",
        "label": "Integrate the missing capability",
        "description": (
            "Close the app (`Ctrl+C` on the make app terminal), open a "
            "dev session, add the missing tool/source/kind following "
            "the new-source waterfall in SKILL.md, run pytest + the "
            "integration audit + Playwright E2E, then restart with "
            "make app and re-ask."
        ),
    },
    {
        "key": "C",
        "label": "One-off in terminal — show result in chat, no card",
        "description": (
            "Use the base Claude Code toolset (WebFetch, Bash, ad-hoc "
            "Python) to answer the request right now and print the "
            "result in the chat. DO NOT create a card — cards are "
            "reserved for quant_radar.tools.* outputs only. This is "
            "an escape hatch for ad-hoc questions, not a way to add "
            "new data sources behind the user's back."
        ),
    },
]


def request_user_decision(
    description: str, *,
    options: list[dict[str, str]] | None = None,
    extra_context: str | None = None,
) -> dict[str, Any]:
    """Return a structured 'not supported — what would you like to do?' menu.

    The agent is expected to call this when the current request cannot
    be satisfied by ``quant_radar.tools.*`` + the documented kinds in
    ``TOOLS.md``. The return value is a structured payload the agent
    reads back to the user. Pass any of the three pre-built options
    (default) or supply a custom list.

    ``description`` is a short prose explanation of WHY the request is
    blocked — e.g. *"You asked for AUM history but only snapshot AUM
    is currently supported."*

    ``extra_context`` is optional — e.g. a suggested integration plan
    the agent can offer alongside option B.
    """
    return {
        "blocked": True,
        "reason": description,
        "extra_context": extra_context,
        "options": options if options is not None else _DEFAULT_OPTIONS,
        "instructions": (
            "Present the options above to the user verbatim. Wait for "
            "their pick (A / B / C or 'Other'). Do NOT freelance — do "
            "not call WebFetch or Bash to build a card. The only "
            "permitted ad-hoc execution path is option C, and only "
            "when the user explicitly chooses it."
        ),
    }


def request_user_decision_yesno(
    description: str, *,
    yes_label: str = "Yes",
    no_label: str = "No",
) -> dict[str, Any]:
    """Sometimes the decision is binary — e.g. *'I can do this via the
    ad-hoc path; want me to?'*. Same shape, simpler menu.
    """
    return request_user_decision(
        description,
        options=[
            {"key": "Y", "label": yes_label, "description": ""},
            {"key": "N", "label": no_label, "description": ""},
        ],
    )


# Literal type hint for downstream typing — what the user picked.
DecisionKey = Literal["A", "B", "C", "Y", "N", "Other"]
