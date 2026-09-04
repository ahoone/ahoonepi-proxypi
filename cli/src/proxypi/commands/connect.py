import os

from pydantic import FilePath

from proxypi.common.config import config
from proxypi.common.options import ProxyIDArgument


def connect(
    proxy_id: ProxyIDArgument,
    lighthouse_private_key_path: FilePath = config.lighthouse_private_key_path,
):
    """
    Replaces the current CLI process with the SSH connection.
    """
    args = [
        "ssh",
        "-i",
        str(lighthouse_private_key_path),
        "-p",
        str(proxy_id + config.ssh_network_base - 2),
        f"{config.proxypi_user}@localhost",
    ]

    os.execvp(args[0], args)
