from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
import ipaddress
from typing import List, Union, Callable, Awaitable


async def check_ip(
    request: Request,
    allowed_networks: List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]],
) -> JSONResponse:
    """
    Used for a page (/check-ip).
    Check what IP the server sees and if it's allowed.
    :param request:
    :param allowed_networks:
    :return:
    """

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


async def filter_ip_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
    allowed_networks: List[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]],
) -> JSONResponse:
    """
    Used for http middleware.
    :param request:
    :param call_next:
    :param allowed_networks:
    :return:
    """

    client_ip = request.client.host
    try:
        client_ip_obj = ipaddress.ip_address(client_ip)
        allowed = any(client_ip_obj in network for network in allowed_networks)
        if not allowed:
            return JSONResponse(
                status_code=403,
                content={"detail": f"Access forbidden from IP: {client_ip}"},
            )
        response = await call_next(request)
        return response
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"detail": f"Unknown error for {client_ip}: {e}"},
        )
