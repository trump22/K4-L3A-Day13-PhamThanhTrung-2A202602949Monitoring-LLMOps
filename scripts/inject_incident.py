from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.challenge import resolve_incident
from app.cli import configure_utf8_stdio

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_CHALLENGE = Path("config/challenge.json")


def main() -> None:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenario",
        choices=["rag_slow", "tool_fail", "cost_spike"],
        help="Chỉ dùng cho practice. Bỏ tham số này để đọc config/challenge.json.",
    )
    parser.add_argument("--disable", action="store_true")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base URL (default: %(default)s)")
    parser.add_argument(
        "--challenge-file",
        type=Path,
        default=DEFAULT_CHALLENGE,
        help="Official released challenge JSON (default: %(default)s)",
    )
    args = parser.parse_args()

    scenario = resolve_incident(args.scenario, challenge_path=args.challenge_file)
    path = f"/incidents/{scenario}/disable" if args.disable else f"/incidents/{scenario}/enable"
    r = httpx.post(f"{args.base_url.rstrip('/')}{path}", timeout=10.0)
    print(r.status_code, r.json())


if __name__ == "__main__":
    main()
