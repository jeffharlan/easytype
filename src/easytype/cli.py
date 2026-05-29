import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="easytype", description="Local voice dictation for Linux")
    parser.add_argument("--passive", action="store_true", help="Run without grabbing the keyboard")
    parser.add_argument("--check", action="store_true", help="Run preflight checks and exit")
    parser.add_argument(
        "--set-hotkey", nargs="?", const="record", choices=["record", "cancel", "repaste"],
        help="Interactively capture a hotkey, then save it",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    print(f"easytype: parsed args = {args}")  # replaced in Task 13


if __name__ == "__main__":
    main()
