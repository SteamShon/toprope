"""Run a domain server with its stderr kept in a file: `python serverwrap.py LOG EXE ARGS...`.

Claude Code starts the probes' MCP servers and keeps their stderr to itself, so a server that dies
at start leaves nothing in the run's records but "failed". This keeps it, beside the probe's
transcript (found in the M1 recheck: every Toprope probe's servers failed, with no reason on record).
"""
import os
import sys

log, exe, *args = sys.argv[1:]
fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
os.dup2(fd, 2)
os.execv(exe, [exe, *args])
