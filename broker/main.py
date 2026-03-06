import asyncio
import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
import ipaddress
import os
import random
import socket
import sys
from typing import List, Dict, Callable

sys.path.insert(0, "/plugins")
import fast_api_ip_middleware

NODE_ROLE = os.getenv("NODE_ROLE").split(",")
assert "LIGHTHOUSE" in NODE_ROLE, "The node should be a lighthouse (ie includes broker) to launch this image"


# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #


# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #


ALLOWED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),  # localhost
    # ipaddress.ip_network("10.0.0.0/24"),      # VPN network
    ipaddress.ip_network("10.0.0.1/32"),  # Lighthouse through VPN
    ipaddress.ip_network("172.16.0.0/12"),  # Docker bridge networks (for dev)
    ipaddress.ip_network(
        "192.168.0.0/16"
    ),  # Docker compose networks (for the proxypi socket)
    ipaddress.ip_network("::1/128"),  # IPv6 localhost
]


app = FastAPI(title="Scraper API", description="Scraper", version="1.0.0")


@app.get("/check-ip")
async def check_ip(request: Request):
    return await fast_api_ip_middleware.check_ip(request, ALLOWED_NETWORKS)


@app.middleware("http")
async def filter_ip_middleware(request: Request, call_next: Callable):
    return await fast_api_ip_middleware.filter_ip_middleware(
        request, call_next, ALLOWED_NETWORKS
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------------------------------------------------------------- #
# -------------------------------------------------------------------------------- #

def call_proxypi(command: str) -> str:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(60)
    sock.connect("/tmp/proxypi.sock")
    sock.sendall((command + "\n").encode())
    chunks = []
    while chunk := sock.recv(4096):
        chunks.append(chunk)
    sock.close()
    return b"".join(chunks).decode()

@app.get("/wireguard-status")
async def wireguard_status():
    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: call_proxypi("ping-wireguard -a")
        )
        # take a look at /proxypi.sh wireguard::ping
        # (called by ./proxypi wireguard-ping -a)
        return {"output": result.splitlines()}
    except Exception as e:
        line = sys.exc_info()[2].tb_lineno
        raise HTTPException(
            status_code=500, detail=f"{type(e).__name__} at line {line}: {str(e)}"
        )

