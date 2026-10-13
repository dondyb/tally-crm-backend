"""Temporary startup diagnostic: shows which database hostnames resolve inside the platform."""

import os
import socket
from urllib.parse import urlparse


def report() -> None:
    try:
        print("[netcheck] resolv.conf:", open("/etc/resolv.conf").read().replace("\n", " | "), flush=True)
    except OSError as exc:
        print("[netcheck] resolv.conf unreadable:", exc, flush=True)
    host = urlparse(os.environ.get("DATABASE_URL", "")).hostname or "crm-db"
    print("[netcheck] DATABASE_URL host:", host, flush=True)
    names = [host, f"{host}-rw"]
    for ns in ("myproject", f"myproject-{host}", "myproject-crm-backend", "default"):
        for svc in (host, f"{host}-rw"):
            names += [f"{svc}.{ns}", f"{svc}.{ns}.svc.cluster.local"]
    for name in names:
        try:
            print(f"[netcheck] OK   {name} -> {socket.gethostbyname(name)}", flush=True)
        except OSError as exc:
            print(f"[netcheck] FAIL {name}: {exc}", flush=True)
