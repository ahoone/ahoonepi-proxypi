from proxypi.common.config import CONFIG_FILEPATH, PROJECT_ROOT, config


def conf():
    """
    Prints the current network configuration.
    """
    print(
        f"Project root: {PROJECT_ROOT}",
        f"Config filepath: {CONFIG_FILEPATH}",
        f"VPN network: {config.wireguard_network}",
        f"VPN available range: 1-{config.network_size}",
        sep="\n",
    )
