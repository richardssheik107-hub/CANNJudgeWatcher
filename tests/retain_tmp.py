"""CI temporary paths are retained; recursive cleanup is prohibited."""
import os
import re
import shutil
import tempfile
from pathlib import Path

import pytest


def _refuse_cleanup(*args, **kwargs):
    raise RuntimeError('Recursive cleanup is prohibited in this workspace')


def pytest_configure(config):
    if config.pluginmanager.hasplugin('tmpdir'):
        raise RuntimeError('Disable pytest tmpdir cleanup before loading retain_tmp')
    shutil.rmtree = _refuse_cleanup


@pytest.fixture
def tmp_path(request):
    root = Path(os.environ['CANNWATCHER_TEST_ARTIFACTS'])
    root.mkdir(parents=True, exist_ok=True)
    name = re.sub(r'[^A-Za-z0-9_-]', '_', request.node.name)[:24]
    return Path(tempfile.mkdtemp(prefix=name + '-', dir=root))
