from __future__ import annotations

import argparse
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import text

from .config import get_settings
from .database import build_engine, build_session_factory
from .demo_seed import roll_demo, seed_demo
from .storage import S3Storage


def main() -> int:
    parser = argparse.ArgumentParser(description="StroyKontrol service utilities")
    parser.add_argument(
        "command",
        choices=["check", "seed-demo", "reset-demo", "roll-demo", "check-storage"],
    )
    parser.add_argument(
        "--date",
        help="Дата показательного дня YYYY-MM-DD; по умолчанию сегодня в Москве",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Подтвердить удаление и пересоздание подготовленных демо-объектов",
    )
    args = parser.parse_args()
    settings = get_settings()
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    if args.command == "check":
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        print("database: ok")
    elif args.command == "check-storage":
        storage = S3Storage(settings)
        storage.ensure_ready()
        print(f"storage: ok ({settings.s3_bucket}/{settings.s3_prefix}/)")
    else:
        if args.command == "reset-demo" and not args.yes:
            parser.error("reset-demo требует явного флага --yes")
        observed_date = (
            datetime.strptime(args.date, "%Y-%m-%d").date()
            if args.date
            else datetime.now(ZoneInfo("Europe/Moscow")).date()
        )
        storage = S3Storage(settings)
        storage.ensure_ready()
        if args.command == "roll-demo":
            result = roll_demo(session_factory, storage, settings, show_day=observed_date)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["status"] == "rolled" else 1
        result = seed_demo(
            session_factory,
            storage,
            settings,
            observed_date=observed_date,
            reset=args.command == "reset-demo",
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if any(
            item.get("state") not in {"completed", "partial"}
            for item in result.get("snapshots", [])
        ):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
