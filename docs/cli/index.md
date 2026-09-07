# ProxyPi CLI

The ProxyPi CLI is responsible for controlling the fleet and simplifying the deployment and operation of its main services.

Its responsibilities include continuous fleet monitoring, software updates, deployment, and manual administrative operations.

## Rationale

The CLI is responsible for managing the fleet and its dependencies. However, it should not itself become a dependency of the remote nodes it manages.

For example, an operation should not work by launching `proxypi` on the lighthouse, connecting to a proxy over SSH, and then invoking `proxypi` again on that proxy. Such a design would require the proxies to maintain an up-to-date version of the CLI before the CLI could update or manage them.

Instead, remote operations should rely only on basic, stable system utilities available on the proxies. The ProxyPi CLI builds on top of these primitives from the lighthouse, where the orchestration logic lives.

This establishes a simple architectural rule:

> **The lighthouse retains control; proxies provide primitives, not orchestration.**

Keeping this boundary in mind helps prevent circular dependencies and keeps the architecture straightforward as ProxyPi evolves.

Function `proxypi.common.core.execute_command` is implemented for this reason on should be the main way of accesing the proxies:

```python
async def execute_command(
    bash_command: str,
    *,
    target: IPv4Address | Port | None = None,
    timeout: float | None = None,
    mode: ExecuteCommandMode = "hold",
    raise_exit_code: bool = True,
    lighthouse_private_key_path: FilePath = config.lighthouse_private_key_path,
    tcp_connection_timeout: int = config.tcp_connection_timeout,
    proxypi_user: str = config.proxypi_user,
) -> tuple[str, timedelta]:
```
