"""NFS (datafiles share) read-only tools: list, stat, find. Never reads file contents.
The mount itself is read-only; path confinement here stops ../ and symlink escapes."""
import fnmatch
import os
import stat as stat_mod
from datetime import datetime, timezone

from .common import audited, jsonable

MAX_ENTRIES = 500
MAX_VISITED = 20000


def root() -> str:
    return os.path.realpath(os.environ.get("NFS_ROOT", "/data/datafiles"))


def resolve(rel: str = "") -> str:
    """Resolve rel under the NFS root, following symlinks; refuse anything outside."""
    base = root()
    path = os.path.realpath(os.path.join(base, rel.lstrip("/")))
    if path != base and not path.startswith(base + os.sep):
        raise ValueError("path escapes the NFS root")
    return path


def _entry(path: str, st: os.stat_result) -> dict:
    return {
        "name": os.path.basename(path),
        "type": "dir" if stat_mod.S_ISDIR(st.st_mode) else "file" if stat_mod.S_ISREG(st.st_mode) else "other",
        "size": st.st_size,
        "mtime": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
        "mode": oct(stat_mod.S_IMODE(st.st_mode)),
    }


def register(mcp):
    @mcp.tool()
    @audited
    def nfs_list(path: str = "", limit: int = 200) -> dict:
        """List a directory under the datafiles share (relative path, '' is the root)."""
        limit = max(1, min(limit, MAX_ENTRIES))
        target = resolve(path)
        entries = []
        with os.scandir(target) as it:
            for de in sorted(it, key=lambda d: d.name):
                if len(entries) >= limit:
                    break
                entries.append(_entry(de.path, de.stat(follow_symlinks=False)))
        return jsonable({"path": os.path.relpath(target, root()), "entries": entries,
                         "truncated": len(entries) >= limit})

    @mcp.tool()
    @audited
    def nfs_stat(path: str) -> dict:
        """Stat one file or directory under the datafiles share."""
        target = resolve(path)
        return jsonable(_entry(target, os.stat(target)))

    @mcp.tool()
    @audited
    def nfs_find(pattern: str, path: str = "", limit: int = 100) -> dict:
        """Find names matching a glob (e.g. '*.csv') under a directory, recursively."""
        limit = max(1, min(limit, MAX_ENTRIES))
        start = resolve(path)
        base = root()
        hits, visited = [], 0
        for dirpath, dirnames, filenames in os.walk(start, followlinks=False):
            for name in dirnames + filenames:
                visited += 1
                if fnmatch.fnmatch(name, pattern):
                    full = os.path.join(dirpath, name)
                    hits.append(os.path.relpath(full, base))
                    if len(hits) >= limit:
                        return {"matches": hits, "truncated": True}
            if visited >= MAX_VISITED:
                return {"matches": hits, "truncated": True}
        return {"matches": hits, "truncated": False}
