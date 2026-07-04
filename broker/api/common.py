from core.Broker import Broker
from fastapi import Request


def get_broker(request: Request) -> Broker:
    return request.app.state.broker
