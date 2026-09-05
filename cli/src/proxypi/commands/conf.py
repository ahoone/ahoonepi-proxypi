from proxypi.common.config import PROJECT_ROOT, config


def conf():
    """
    Print the current network configuration.
    """
    print(
        f"Project root: {PROJECT_ROOT}",
        f"VPN network: {config.wireguard_network}",
        f"VPN available range: 1-{config.network_size}",
        sep="\n",
    )
