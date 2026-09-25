"""Robot lifecycle simulation HTTP contract, mounted by fulfillment."""
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field, StrictBool, field_validator
from uuid import UUID
import robot_lifecycle

router = APIRouter()


class ChargingInput(BaseModel):
    charging: StrictBool
    revision: int = Field(ge=1)


class TaskFailureInput(BaseModel):
    request_id: UUID
    assignment_token: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def reason_is_not_blank(cls, value):
        if not value.strip():
            raise ValueError("reason must not be blank")
        return value


class TaskKillInput(BaseModel):
    request_id: UUID
    assignment_token: str = Field(min_length=1, max_length=200)
    reason: str = Field(
        default="Fleet Simulator operator killed the assigned function.",
        min_length=1, max_length=2000,
    )

    @field_validator("reason")
    @classmethod
    def reason_is_not_blank(cls, value):
        if not value.strip():
            raise ValueError("reason must not be blank")
        return value


def role(value, write=False):
    if value not in ({"fleet"} if write else {"fleet", "supervisor", "admin"}):
        raise HTTPException(403, "Fleet persona required" if write else "Persona cannot view lifecycle")


@router.get("/lifecycle")
def lifecycle(x_demo_persona: str = Header("supervisor", alias="X-Demo-Persona")):
    import fulfillment_api as host
    role(x_demo_persona)
    with host.db_transaction() as db:
        now = host.utc_now()
        robot_lifecycle.reconcile(db, now, host.source_rows)
        return robot_lifecycle.snapshot(db, now)


@router.post("/lifecycle/{resource_id}/charging")
def charging(resource_id: str, payload: ChargingInput,
             x_demo_persona: str = Header(None, alias="X-Demo-Persona")):
    import fulfillment_api as host
    role(x_demo_persona, write=True)
    with host.db_transaction() as db:
        now = host.utc_now()
        robot_lifecycle.reconcile(db, now, host.source_rows)
        robot_lifecycle.set_charging(db, resource_id, payload.charging, payload.revision, now)
        return next(r for r in robot_lifecycle.snapshot(db, now)["resources"] if r["resource_id"] == resource_id)


@router.post("/assign-tasks")
def assign_tasks():
    import fulfillment_api as host
    import fulfillment_v2
    with host.db_transaction() as db:
        now = host.utc_now()
        counts = {}
        fulfillment_v2.executor_once(db, now, host.source_rows, host._append_event,
                                    force_assignment=True, stats=counts)
        scheduler = robot_lifecycle.snapshot(db, now)["scheduler"]
        return {**counts, "ran_at": host.iso(now), "next_assignment_at": scheduler["next_assignment_at"]}


@router.get("/lifecycle/tasks")
def tasks(x_demo_persona: str = Header("supervisor", alias="X-Demo-Persona")):
    import fulfillment_api as host
    role(x_demo_persona)
    with host.db_transaction() as db:
        now = host.utc_now()
        robot_lifecycle.reconcile(db, now, host.source_rows)
        return {
            "tasks": robot_lifecycle.lifecycle_tasks(db),
            "server_time": host.iso(now),
        }


@router.post("/lifecycle/tasks/{task_id}/fail")
def fail_task(
    task_id: str,
    payload: TaskFailureInput,
    x_demo_persona: str = Header(None, alias="X-Demo-Persona"),
):
    import fulfillment_api as host
    role(x_demo_persona, write=True)
    with host.db_transaction() as db:
        now = host.utc_now()
        return robot_lifecycle.fail_task(
            db, task_id, str(payload.request_id), payload.assignment_token,
            payload.reason, now, host._append_event,
        )


@router.post("/lifecycle/tasks/{task_id}/kill")
def kill_task(
    task_id: str,
    payload: TaskKillInput,
    x_demo_persona: str = Header(None, alias="X-Demo-Persona"),
):
    import fulfillment_api as host
    role(x_demo_persona, write=True)
    with host.db_transaction() as db:
        now = host.utc_now()
        robot_lifecycle.reconcile(db, now, host.source_rows)
        return robot_lifecycle.kill_task(
            db, task_id, str(payload.request_id), payload.assignment_token,
            payload.reason, now, host.source_rows, host._append_event,
        )


@router.post("/lifecycle/resources/{resource_id}/recover")
def recover_resource(
    resource_id: str,
    x_demo_persona: str = Header(None, alias="X-Demo-Persona"),
):
    import fulfillment_api as host
    role(x_demo_persona, write=True)
    with host.db_transaction() as db:
        return robot_lifecycle.recover_resource(
            db, resource_id, host.utc_now(), host._append_event
        )