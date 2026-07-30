from fastapi import Request

from broker.core.Broker import Broker


def get_broker(request: Request) -> Broker:
    return request.app.state.broker
