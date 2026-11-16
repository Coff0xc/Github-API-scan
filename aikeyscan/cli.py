"""Installable CLI. Delegates to scanner_main.main with unchanged flags."""

from __future__ import annotations

import sys
from typing import Optional, Sequence


def main(argv: Optional[Sequence[str]] = None) -> None:
    if argv is not None:
        sys.argv = [sys.argv[0], *list(argv)]
    from scanner_main import main as run

    run()


if __name__ == "__main__":
    main()
