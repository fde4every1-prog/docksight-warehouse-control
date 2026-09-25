import argparse
import json

from warehouse_control.allocator.filter_score import allocate_for_task, rejection_reasons
from warehouse_control.diagnostics import run
from warehouse_control.fulfillment.cutoff import assess_cutoff
from warehouse_control.injects.replay import replay_inject


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "command",
        choices=["diagnostics", "allocate", "cutoff", "explain", "inject", "evals", "readiness"],
    )
    p.add_argument("--task-id")
    p.add_argument("--order-id")
    p.add_argument("--robot-id")
    p.add_argument("--inject-id")
    a = p.parse_args()
    if a.command == "diagnostics":
        print(json.dumps(run(), indent=2))
        return
    if a.command == "allocate":
        print(json.dumps(allocate_for_task(a.task_id, inject_id=a.inject_id), indent=2))
        return
    if a.command == "cutoff":
        print(json.dumps(assess_cutoff(a.order_id), indent=2))
        return
    if a.command == "explain":
        print(json.dumps(rejection_reasons(a.robot_id, a.task_id), indent=2))
        return
    if a.command == "inject":
        print(json.dumps(replay_inject(a.inject_id, a.task_id), indent=2))
        return
    if a.command == "evals":
        from warehouse_control.evals.harness import run_harness

        summary = run_harness(write_artifacts=True)
        print(
            json.dumps(
                {
                    "pass_count": summary["pass_count"],
                    "fail_count": summary["fail_count"],
                    "unsafe_expired_cert_assigns_uc1": summary["unsafe_expired_cert_assigns_uc1"],
                    "operational_success": summary["operational_success"],
                    "must_not_failures": summary["must_not_failures"],
                    "scorecard": "evals/scorecard.md",
                },
                indent=2,
            )
        )
        return
    if a.command == "readiness":
        from warehouse_control.evals.adversarial import (
            compute_kpi_before_after,
            run_simultaneous_pressure,
            write_trace,
        )

        pressure = run_simultaneous_pressure()
        write_trace(pressure)
        kpis = compute_kpi_before_after()
        print(
            json.dumps(
                {
                    "must_not_ok": pressure["must_not_ok"],
                    "physical_control": pressure["physical_control"],
                    "chosen_is_expired_cert": pressure["chosen_is_expired_cert"],
                    "kpis": kpis,
                    "trace": "evals/traces/PROMPT-15-SIMULTANEOUS.json",
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
