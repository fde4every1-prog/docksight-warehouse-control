"""DecisionEngine: ALLOW / DENY / ABSTAIN. Never applies OT. Does not import executor."""

SAFETY_INTENTS = frozenset(
    {"release_zone", "speed_change", "estop_bypass", "cert_waiver"}
)

_EXEC = {"applied": False, "physical_control": "disabled"}


def _out(decision: str, reason_codes: list[str]) -> dict:
    return {
        "decision": decision,
        "reason_codes": reason_codes,
        "execution": dict(_EXEC),
    }


def decide(action_proposal: dict) -> dict:
    proposal = action_proposal or {}
    intent = proposal.get("intent") or ""

    if intent in SAFETY_INTENTS:
        return _out("DENY", ["G7"])

    if intent == "replay_all_fleet_tasks" or proposal.get("ack") == "UNKNOWN":
        return _out("ABSTAIN", ["G8", "UNKNOWN_ACK"])

    if intent == "allocate_as_known":
        inv = proposal.get("inventory") or {}
        if inv.get("uncertain"):
            return _out("ABSTAIN", ["G5"])
        return _out("ABSTAIN", ["G8"])

    if intent == "close_order":
        task = proposal.get("task") or {}
        if task.get("conflict") or task.get("completable") is False:
            return _out("DENY", ["G6"])
        return _out("ABSTAIN", ["G8"])

    if intent == "miss_cutoff":
        return _out("ALLOW", ["T1_MISS_CUTOFF"])

    return _out("ABSTAIN", ["G8"])
