import argparse
import datetime
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from app.config import settings


def pg_url() -> str:
    return settings.database_url.split("+", 1)[0] if "+" in settings.database_url else settings.database_url


def main():
    ap = argparse.ArgumentParser(description="Backup Postgres database + report files")
    ap.add_argument("--out", default=os.path.join(settings.data_dir, "backups"))
    ap.add_argument("--skip-files", action="store_true", help="skip copying extracted/reports data dir")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    dump_path = os.path.join(args.out, f"backup_{stamp}.sql")

    print(f"dumping {pg_url()} -> {dump_path}")
    try:
        with open(dump_path, "wb") as fh:
            subprocess.run(["pg_dump", pg_url()], stdout=fh, check=True)
        print(f"db dump ok: {dump_path} ({os.path.getsize(dump_path)} bytes)")
    except FileNotFoundError:
        print("pg_dump not found - install postgresql client tools")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"pg_dump failed: {e}")
        sys.exit(1)

    if not args.skip_files:
        for sub in ("reports", "uploads", "models"):
            src = os.path.join(settings.data_dir, sub)
            if os.path.isdir(src):
                dst = os.path.join(args.out, f"files_{stamp}", sub)
                os.makedirs(dst, exist_ok=True)
                if os.name == "nt":
                    subprocess.run(["robocopy", src, dst, "/E", "/NFL", "/NDL", "/NJH", "/NJS"], check=False)
                else:
                    subprocess.run(["cp", "-r", src, dst], check=False)
                print(f"copied {src} -> {dst}")
    print("done. schedule daily: cron or Task Scheduler calling this script.")


if __name__ == "__main__":
    main()
