import asyncio
import socket

SOCKET_PROXYPI = "/tmp/proxypi.sock"

async def run(command: str):

    def _call(command: str) -> str:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(60)
        sock.connect(SOCKET_PROXYPI)
        sock.sendall((command + "\n").encode())
        chunks = []
        while chunk := sock.recv(4096):
            chunks.append(chunk)
        sock.close()
        return b"".join(chunks).decode()

    return await asyncio.get_event_loop().run_in_executor(
        None, lambda: _call(command)
    )
