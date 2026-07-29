from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_archive_environment_root_is_lexically_normalized(tmp_path: Path) -> None:
    configured = tmp_path / "unused-segment" / ".." / "archive"
    environment = os.environ.copy()
    environment["DJRMCP_ARCHIVE_ROOT"] = str(configured)

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from djrmcp_finder.archive import DEFAULT_ARCHIVE_BASE; "
                "print(DEFAULT_ARCHIVE_BASE)"
            ),
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )

    assert completed.stdout.strip() == os.path.abspath(configured)
