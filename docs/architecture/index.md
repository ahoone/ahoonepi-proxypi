# `ahoonepi-proxypi` architecture rationale

The repository hosts two coupled codebases:

- the `proxypi` CLI which provides management tools for the network,
- the components that run the scraping infrastructure.

`proxypi` is a unique reference to the CLI, while `ahoonepi` is a reference to all services apart from the CLI.

## Multi-agent model

The network is designed on the multi-agents model of "orchestrator-workers", very similarly to `Ansible`.

`proxypi` differs in the way that it needs to be first installed on the remote worker and initialized. It was conceived to establish and maintain SSH reverse tunnels on networks you are not administrator.

## Deployment model

The other convenience of having those two joined, is to incorporate functions to restart and update the services at will. The service run inside `docker` containers that need to be managed.

## Threat model

Some thumb rules to drive the threat model:

- every proxy could be compromised,
- `scraper` component runs a `chromium` browser, with all the risks it implies despite actions being limited,
- node isolation should be strictly enforced and the lighthouse is the only cornerstone.

Given that, the lighthouse compromition and its recreation are not handled.

## Rights/permissions management

There are 4 users to consider on the lighthouse:

- `root`,
- `LIGHTHOUSE_DUMMY_USER`, which is the one the proxies funnels through the SSH, that does not have any permission to execute nor read code of any kind,
- `LIGTHOUSE_SERVICE_USER`, which only purpose is to own the the lighthouse' private keys and make them accessible to the user without `sudo`,
- the running user, that uses the CLI...

The files' permissions to consider on the **host**:

- the CLI is installed through `uv` to `~/.local/share/uv/tools/ahoonepi-proxypi`,
- the repository is installed to `/opt/ahoonepi-proxypi` and is owned by `root`,
- the config files are saved in `/etc/ahoonepi-proxypi`,
- the proxies' SSH public keys in `~/.ssh` of the `LIGHTHOUSE_SERVICE_USER`,
- the lighthouse's SSH private keys in `/var/lib/ahoonepi-proxypi` and is owned by `LIGHTHOUSE_SERVICE_USER`,
- the proxies' WireGuard public keys in `/etc/wireguard`,
- the lighthouse WireGuard private key in `/etc/wireguard`.
