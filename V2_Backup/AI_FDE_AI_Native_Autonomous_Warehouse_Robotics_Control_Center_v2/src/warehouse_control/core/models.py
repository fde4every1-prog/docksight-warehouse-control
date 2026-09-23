from dataclasses import dataclass

@dataclass
class RobotState:
    robot_id: str
    available: bool
    battery_soc: int
    safety_cert_status: str
    health_status: str
