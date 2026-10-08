import argparse

from .config import Settings
from .db import make_engine, session_factory
from .domain import utcnow
from .models import User
from .seed import seed
from .services import Service


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["seed", "reconcile"])
    args = parser.parse_args()
    settings = Settings.from_env()
    settings.validate()
    with session_factory(make_engine(settings.database_url)).begin() as db:
        if args.command == "seed":
            print({"seeded": seed(db), "mode": "DEMO"})
        else:
            actor = db.get(User, "admin")
            if not actor:
                raise SystemExit("Run seed first.")
            print(Service(db, actor, utcnow(), settings, "cli-reconcile").reconcile())


if __name__ == "__main__":
    main()
