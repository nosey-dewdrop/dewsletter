#!/usr/bin/env python3
"""An ephemeral PostgreSQL cluster, born and buried inside one test class.

Why this exists: the seat arithmetic is not Python, it is a trigger. A test
that reads schema.sql as a string can prove the advisory lock LINE is present;
only a real cluster with twenty real sessions can prove the lock WORKS. Without
the lock this harness measures 119 subscribers in a 100-seat table. That number
is the whole reason the lock line exists, so the test that produces it has to
run against a real server.

It never touches the production Supabase. It runs initdb into a temp dir,
listens on a unix socket in that same temp dir (no TCP port, so no collision
with a developer's local postgres), and is removed on teardown.

There is no psycopg2 or pg8000 on this machine and pip is banned, so every
statement goes out through `psql` as a subprocess. That is slower than a driver
and completely sufficient: the concurrency test WANTS twenty separate OS
processes, since twenty threads sharing one connection could not race at all.

Vanilla PostgreSQL has no `anon` role -- that is a Supabase creation -- so the
harness creates it before loading schema.sql, otherwise every `to anon` policy
in the file would abort the load.

If initdb is not installed the module reports unavailable and the behavioural
tests skip, which is what keeps CI green on a runner without postgres.
"""
# `str | None` in a signature is evaluated at def time, which is a TypeError on
# Python 3.9 (the macOS system interpreter). CI runs 3.12 and would not have
# noticed. Deferring annotations keeps the harness importable everywhere, so a
# missing-postgres run reaches the skip instead of an import crash.
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
SCHEMA = HERE.parent / "schema.sql"

# Homebrew keeps postgresql@15 keg-only, so it is not on a default PATH.
_BREW_BIN = "/opt/homebrew/opt/postgresql@15/bin"


def _tool(name: str) -> str | None:
    """Absolute path to a postgres binary, PATH first, then the keg."""
    found = shutil.which(name)
    if found:
        return found
    candidate = Path(_BREW_BIN) / name
    return str(candidate) if candidate.exists() else None


def available() -> bool:
    """True when a cluster can actually be built here."""
    return all(_tool(n) for n in ("initdb", "pg_ctl", "psql"))


class Cluster:
    """One throwaway cluster. Start it, talk to it, stop it."""

    def __init__(self) -> None:
        self.dir = Path(tempfile.mkdtemp(prefix="sightstone_pg_"))
        self.data = self.dir / "data"
        self.sock = self.dir / "sock"
        self.started = False

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        self.sock.mkdir()
        subprocess.run(
            [_tool("initdb"), "-D", str(self.data), "--auth=trust",
             "--no-sync", "-U", "postgres", "--encoding=UTF8"],
            check=True, capture_output=True, text=True)
        # No TCP listener at all: a unix socket inside the temp dir cannot
        # collide with anything else on the machine, and cannot be reached
        # from off-box.
        subprocess.run(
            [_tool("pg_ctl"), "-D", str(self.data), "-w", "-l",
             str(self.dir / "log"), "-o",
             f"-k {self.sock} -c listen_addresses='' "
             f"-c max_connections=100 -c fsync=off", "start"],
            check=True, capture_output=True, text=True)
        self.started = True

    def stop(self) -> None:
        if self.started:
            subprocess.run([_tool("pg_ctl"), "-D", str(self.data),
                            "-m", "immediate", "-w", "stop"],
                           capture_output=True, text=True)
            self.started = False
        shutil.rmtree(self.dir, ignore_errors=True)

    # -- talking to it -----------------------------------------------------
    def _argv(self) -> list[str]:
        return [_tool("psql"), "-h", str(self.sock), "-U", "postgres",
                "-d", "postgres", "-v", "ON_ERROR_STOP=1", "-X", "-q"]

    def run(self, sql: str, check: bool = True) -> subprocess.CompletedProcess:
        """Run SQL, return the finished process. stdout is raw psql output."""
        proc = subprocess.run(self._argv() + ["-c", sql],
                              capture_output=True, text=True)
        if check and proc.returncode != 0:
            raise RuntimeError(f"psql failed on {sql!r}:\n{proc.stderr}")
        return proc

    def run_file_text(self, sql_text: str) -> None:
        """Load a whole script (schema.sql, possibly mutated) from stdin."""
        proc = subprocess.run(self._argv() + ["-f", "-"], input=sql_text,
                              capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"psql script failed:\n{proc.stderr}")

    def scalar(self, sql: str) -> str:
        """One value, no headers, no padding."""
        proc = subprocess.run(self._argv() + ["-t", "-A", "-c", sql],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"psql failed on {sql!r}:\n{proc.stderr}")
        return proc.stdout.strip()

    def count(self, sql: str) -> int:
        return int(self.scalar(sql))

    def spawn(self, sql: str) -> subprocess.Popen:
        """Start a session and do NOT wait for it. Used to force a real race."""
        return subprocess.Popen(self._argv() + ["-c", sql],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)

    # -- schema ------------------------------------------------------------
    def load_schema(self, text: str | None = None) -> None:
        """Create the missing Supabase role, then load schema.sql (or a
        mutated copy of it, which is how the mutation tests work)."""
        self.run("create role anon;")
        self.run_file_text(text if text is not None else SCHEMA.read_text())


def schema_text() -> str:
    return SCHEMA.read_text()


def env_note() -> str:
    return (f"initdb={_tool('initdb')} psql={_tool('psql')} "
            f"pid={os.getpid()}")
