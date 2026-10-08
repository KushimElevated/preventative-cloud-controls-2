import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = "postgresql+psycopg://controls:local-demo@localhost:5432/controls"
    app_env: str = "local"
    auth_mode: str = "demo"
    live_deployment: bool = False
    evidence_hours: int = 24
    session_hours: int = 2

    @classmethod
    def from_env(cls):
        return cls(
            database_url=os.getenv("DATABASE_URL", cls.database_url),
            app_env=os.getenv("APP_ENV", "local"),
            auth_mode=os.getenv("AUTH_MODE", "demo"),
            live_deployment=os.getenv("LIVE_DEPLOYMENT", "false").lower() not in ("false", "0", ""),
        )

    def validate(self):
        if self.live_deployment:
            raise RuntimeError("Live deployment is not implemented and cannot be enabled.")
        if self.app_env not in {"local", "test"} or self.auth_mode != "demo":
            raise RuntimeError("Only local/test demo authentication is implemented. Configure enterprise auth before deployment.")
