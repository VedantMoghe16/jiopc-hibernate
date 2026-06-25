"""Enable ``python -m jiopc_hibernate <command>``."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
