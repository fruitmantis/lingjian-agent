"""Create a clean, synthetic E2E database in the dedicated /tmp directory."""

import os
import shutil
from pathlib import Path


def main() -> None:
    database = Path(os.environ["LINGJIAN_DATABASE_PATH"]).resolve()
    validation_root = Path("/tmp/lingjian-enablement-e2e").resolve()
    if database.parent != validation_root or database.name != "app.db":
        raise RuntimeError("refusing to reset a database outside the dedicated E2E directory")
    shutil.rmtree(validation_root, ignore_errors=True)
    validation_root.mkdir(parents=True)
    from backend.tests.support.seed_validation_db import seed
    seed()


if __name__ == "__main__":
    main()
