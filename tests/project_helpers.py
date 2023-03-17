"""Common helpers shared between test_real_project and test_sample_projects."""
import hashlib
import logging
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List

import pytest

logger = logging.getLogger(__name__)


@dataclass
class CachedExperimentVenv:
    """A virtualenv used in a sample or real-world experiment.

    This is a test helper to create and reuse virtualenvs that contain real
    packages used in our integration tests. The goal is that venvs are created
    _once_ and reused as long as the commands used to create them and install
    packages into them remain unchanged. These use pytest's caching
    infrastructure meaning that the venvs typically end up living under
    ~/.cache/pytest/d/...
    """

    requirements: List[str]  # PEP 508 requirements, passed to 'pip install'

    def venv_script_lines(self, venv_path: Path) -> List[str]:
        return (
            [
                f"rm -rf {venv_path}",
                f"python3 -m venv {venv_path}",
                f"{venv_path}/bin/pip install --upgrade pip",
            ]
            + [
                f"{venv_path}/bin/pip install {shlex.quote(req)}"
                for req in self.requirements
            ]
            + [
                f"touch {venv_path}/.installed",
            ]
        )

    def venv_hash(self) -> str:
        """Returns a hash that depends on the venv script and python version.

        The installation script will change if the code to setup the venv in
        venv_script_lines() changes, or if the requirements of the experiment
        changes. It will also be different for different Python versions.
        The Python version currently used to run the tests is used to compute
        the hash and create the venv.
        """
        dummy_script = self.venv_script_lines(Path("/dev/null"))
        py_version = f"{sys.version_info.major},{sys.version_info.major}"
        script_and_version_bytes = ("".join(dummy_script) + py_version).encode()
        return hashlib.sha256(script_and_version_bytes).hexdigest()

    def __call__(self, cache: pytest.Cache) -> Path:
        """Get this venv's dir and create it if necessary.

        The venv_dir is where we install the dependencies of the current
        experiment. It is keyed by the sha256 checksum of the requirements
        file and the script we use for setting up the venv. This way, we
        don't risk using a previously cached venv for a different if the
        script or the requirements to create that venv change.
        """
        # We cache venv dirs using the hash from create_venv_hash
        cached_str = cache.get(f"fawltydeps/{self.venv_hash()}", None)
        if cached_str is not None and Path(cached_str, ".installed").is_file():
            return Path(cached_str)  # already cached

        # Must run the script to set up the venv
        venv_dir = Path(cache.mkdir(f"fawltydeps_venv_{self.venv_hash()}"))
        logger.info(f"Creating venv at {venv_dir}...")
        venv_script = self.venv_script_lines(venv_dir)
        subprocess.run(
            " && ".join(venv_script),
            check=True,  # fail if any of the commands fail
            shell=True,  # pass multiple shell commands to the subprocess
        )
        # Make sure the venv has been installed
        assert (venv_dir / ".installed").is_file()
        cache.set(f"fawltydeps/{self.venv_hash()}", str(venv_dir))
        return venv_dir
