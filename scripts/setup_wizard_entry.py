import argparse
from pathlib import Path

from codex_funplay_bridge.installer_check import check_installer
from codex_funplay_bridge.setup_wizard import main


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Codex-Funplay Bridge setup")
    parser.add_argument("--self-check", type=Path, metavar="REPORT_JSON", help="Verify packaged resources and deployment in a temporary directory")
    args = parser.parse_args()
    if args.self_check is not None:
        raise SystemExit(check_installer(args.self_check))
    main()
