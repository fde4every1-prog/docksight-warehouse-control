"""ActionExecutor stub. OT apply is always refused (I10). Copilot must not import this."""


def execute(decision=None) -> dict:
    return {
        "applied": False,
        "physical_control": "disabled",
        "reason": "I10",
        "decision": decision,
    }
