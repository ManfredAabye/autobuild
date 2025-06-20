from __future__ import annotations
import logging
import subprocess
from pathlib import Path
from typing import NamedTuple

from autobuild.common import cmd, has_cmd, is_env_disabled
from autobuild.scm.base import Semver, date

"""
If a version_file attribute is not present in autobuild.xml then autobuild will
attempt to resolve package version from source control management (SCM) metadata.
Only git is supported at this time.

## Versioning scheme

Autobuild SCM version behavior takes the following into consideration:

- The latest tag with a version number
- The distance from this tag
- Whether the environment is "dirty" (has uncommitted changes)

This information is used to construct a version:

- clean with no distance: {current}
- clean with distance:    {next}-dev{distance}.g{revision}
- dirty:                  {next}-dev{distance}.g{revision}.d{YYYYMMDD}

The {next} tag is the current semver value + a patch bump, ex. 1.0.0 -> 1.0.1

This behavior closely matches setuptools_scm, deviating to match Semantic
Versioning rather than PEP 440

## Environment variables

SCM version resolution can be disabled by setting the following environment
variables to a falsey value (0, f, no, false)

- AUTOBUILD_SCM        - disable SCM version resolution
- AUTOBUILD_SCM_SEARCH - disable walking up parent directories to search for SCM root
"""

__all__ = ["get_version"]

log = logging.getLogger(__name__)
MAX_GIT_SEARCH_DEPTH = 20


class GitMeta(NamedTuple):
    dirty: bool
    distance: int
    commit: str  # Short commit hash
    version: Semver | str


def _find_repo_dir(start: Path, level: int = 0) -> Path | None:
    if level >= MAX_GIT_SEARCH_DEPTH:
        return None
    if (start / ".git").is_dir():
        return start
    if is_env_disabled("AUTOBUILD_SCM_SEARCH"):
        return None
    if start.parent == start:
        return None
    return _find_repo_dir(start.parent, level + 1)


def _parse_describe(describe: str) -> GitMeta:
    log.debug(f"parsing git describe {describe}")
    dirty = describe.endswith("-dirty")
    if dirty:
        describe = describe[:-6]
    raw_tag, distance, commit = describe.rsplit("-", 3 if dirty else 2)[-3:]
    return GitMeta(
        dirty=dirty,
        distance=int(distance),
        commit=commit[1:],
        version=Semver.parse(raw_tag) or raw_tag.lstrip("v"),
    )


class Git:
    repo_dir: Path | None

    def __init__(self, root: str):
        self.repo_dir = _find_repo_dir(Path(root))

    def _git(self, *args) -> subprocess.CompletedProcess[str]:
        log.debug(f"running git command: {' '.join(args)}")
        return cmd("git", "-C", str(self.repo_dir), *args)

    def describe(self) -> str:
        p = self._git("describe", "--dirty", "--tags", "--long", "--match", "*[0-9]*")
        return p.stdout

    @property
    def revision(self) -> str | None:
        return self._git("rev-parse", "HEAD").stdout if self.repo_dir else None

    @property
    def url(self) -> str | None:
        return (
            self._git("remote", "get-url", "origin").stdout if self.repo_dir else None
        )

    @property
    def branch(self) -> str | None:
        return (
            self._git("rev-parse", "--abbrev-ref", "HEAD").stdout
            if self.repo_dir
            else None
        )

    @property
    def version(self) -> str | None:
        if not self.repo_dir:
            log.debug("no git root found, returning null version")
            return None
        meta = _parse_describe(self.describe())
        next_version = (
            meta.version.next if isinstance(meta.version, Semver) else meta.version
        )
        if meta.dirty:
            return f"{next_version}-dev{meta.distance}.g{meta.commit}.d{date()}"
        elif meta.distance:
            return f"{next_version}-dev{meta.distance}.g{meta.commit}"
        else:
            return str(meta.version)


def new_client(root: str) -> Git | None:
    if not has_cmd("git"):
        log.warning("git command not available, skipping git version detection")
        return None
    return Git(root)


def get_version(root: str) -> str | None:
    git = new_client(root)
    return git.version if git else None
