from proxypi.common.config import config
from proxypi.common.types import NodeID, Port, ProxyID


def listen_ports(
    ssh_network_base: Port = config.ssh_network_base,
    network_size: int = config.network_size,
) -> list[Port]:
    """
    Inspects directly the kernel socket table at `/proc/net/tcp`.

    Args:
        ssh_network_base (Port): Description, optional (default: config.ssh_network_base).
        network_size (int): Description, optional (default: config.network_size).

    Returns:
        list[Port]: Description.
    """

    inspection_range: list[Port] = [x + ssh_network_base for x in range(network_size)]

    with open("/proc/net/tcp") as f:
        lines = f.readlines()

    header_row = lines[0].split()
    rows = [dict(zip(header_row, line.split())) for line in lines[1:]]

    found: list[Port] = []
    for row in rows:
        address, port = row["local_address"].split(":")
        address = int(address, 16)
        port = int(port, 16)
        # checks the status is LISTEN (cf `include/net/tcp_states.h`)
        # checks we're on the host
        if int(row["st"], 16) != 10 or address != 0 or port not in inspection_range:
            continue
        found.append(port)

    return found


def listen_proxy_ids() -> list[ProxyID]:
    """
    Does not include the lighthouse, identified by `None`.
    """
    ports: list[Port] = listen_ports()
    return [port - config.ssh_network_base + 2 for port in ports]


def listen_node_ids(lighthouse_id=config.lighthouse_id) -> list[NodeID]:
    """
    Includes the lighthouse id.
    """
    return [lighthouse_id, *listen_proxy_ids()]
