import os
import tempfile

# Must be set before app.config is imported, so tests never touch the real database or uploads.
os.environ["GRSE_VAR_DIR"] = tempfile.mkdtemp(prefix="grse-test-")

import pytest

from scripts.make_samples import make_all


@pytest.fixture(scope="session")
def samples(tmp_path_factory):
    out = tmp_path_factory.mktemp("samples")
    make_all(out)
    return out
