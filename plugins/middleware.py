import ipaddress
from typing import Awaitable, Callable, List, Union

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse


def add_middleware(
    app: FastAPI,
    allowed_networks: List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]],
) -> None:

    @app.get("/check-ip", include_in_schema=False)
    async def check_ip(
        request: Request,
    ) -> JSONResponse:
        client_ip = request.client.host
        x_forwarded_for = request.headers.get("X-Forwarded-For")
        x_real_ip = request.headers.get("X-Real-IP")

        try:
            client_ip_obj = ipaddress.ip_address(client_ip)

            network_checks = {
                str(network): client_ip_obj in network for network in allowed_networks
            }
            allowed = any(client_ip_obj in network for network in allowed_networks)

            return {
                "received_ip": client_ip,
                "x_forwarded_for": x_forwarded_for,
                "x_real_ip": x_real_ip,
                "is_allowed": allowed,
                "network_checks": network_checks,
                "allowed_networks": [str(net) for net in allowed_networks],
            }
        except ValueError as e:
            return {
                "received_ip": client_ip,
                "x_forwarded_for": x_forwarded_for,
                "x_real_ip": x_real_ip,
                "is_allowed": False,
                "error": f"Invalid IP address: {str(e)}",
                "allowed_networks": [str(net) for net in allowed_networks],
            }

    @app.middleware("http")
    async def filter_ip_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        client_ip = request.client.host
        try:
            client_ip_obj = ipaddress.ip_address(client_ip)
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={"detail": f"Invalid IP address: {client_ip}"},
            )

        allowed = any(client_ip_obj in network for network in allowed_networks)
        if not allowed:
            return JSONResponse(
                status_code=403,
                content={"detail": f"Access forbidden from IP: {client_ip}"},
            )

        return await call_next(request)
