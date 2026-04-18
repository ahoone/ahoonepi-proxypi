# ahoonepi-proxypi

Repository hosting the infrastructure for all the Pis (installation + proxypi package + components).

## TO DO

- You can be both lighthouse and proxy for an extented network (not possible for now, wireguard configuration is overwritten for the steps of LIGHTHOUSE and PROXY)
- forwarding websites (livebox/# and ahoonepi.fr:81 (nginx proxy manager) for distant access) and 8080 and 8000 (broker and scraper)
- Nginx Proxy Manager web interface is accessible on localhost, port `81`, but is not exposed to the internet for security reasons.
- Should add a crontab jobs and a small logs files to automatically ping the proxies to get their status.

*It is ducking not good because flags' parameters are also treated as flags (not arguments for the function)*

| Arg.             | For:                                                                  |
|------------------|-----------------------------------------------------------------------|
| -w (ping...)     | web format (list of dictionnaries)                                    |
| -h               | human readable                                                        |
| -l               | logs                                                                  |
| -nwrg            | warnings (terminal window too small)                                  |
| swarm-execute -o | get output                                                            |
| ping-cloudflare  | Test if the proxy is able to bypass cloudflare. (nyi)                 |
| restart          | [restart]="-a -b -s -n node_id"                                       |


## Initialization

### Download

```bash
git clone https://github.com/ahoone/ahoonepi-proxypi .
cd ahoonepi-proxy
```

#### `.env`

```bash
ALLOWED_NETWORKS_BROKER="placeholder"
ALLOWED_NETWORKS_SCRAPER="placeholder"
GIT_BRANCH="main"
GIT_HOSTING_PROVIDER="https://github.com/ahoone"
GIT_REPOSITORY="ahoonepi-proxypi"
HTTP_PORT_BROKER="8080"
HTTP_PORT_SCRAPER="8000"
LIGHTHOUSE_DUMMY_USER=""
LIGHTHOUSE_IP=""
LIGHTHOUSE_SSH_PORT=""
LIGHTHOUSE_WIREGUARD_LISTEN_PORT=""
LIGHTHOUSE_WIREGUARD_PUBLIC_KEY=""
NODE_ROLE="LIGHTHOUSE,SCRAPER,DDNS_UPKEEPER"
OVH_HOST=""
OVH_PASS=""
OVH_USER=""
PROXY_ID=""
```

Roles and components associated:
- `LIGHTHOUSE` : accepts connections on the specified range and controls them
- `PROXY` : connects to a lighthouse
- `SCRAPER` : uses its scraper component
- `NAS` : joins the lighthouse storage infrastructure

```bash
./init.sh
sudo reboot
```


### Scripts

## Access remote to the server

`SSHFS` is not perfect (unproperly dismount when inactive) and makes the connection crashes if not properly done.

To mount the remote server:
```bash
sudo apt install sshfs
sudo mkdir /mnt/remote
sudo sshfs -o allow_other,default_permissions user@device:/home/user /mnt/remote
```

And to disconnect:
```bash
sudo fusermount -u /mnt/remote
```

## Main commands

### Proxies management

Add the alias for the `proxypi` library:
```bash
source .bash_aliases
proxypi
```

> **It is absolutely normal for wireguard ping to be ~3ms, about 150 times faster than SSH connection, which includes much more steps.**

> **Wireguard default VPN host is 10.0.0.1 so the first ahoonepi proxy is 10.0.0.2 (ahoonepi-proxy-2).**


### Scraper component

The scraper API runs permanently.
(Reusing an expired session creates a new one that overrides the expired one.)

> The same container is deployed on the proxies.

```bash
docker compose -f scraper/docker-compose.yml --env-file .env up --build -d
```

```bash
docker compose -f scraper/docker-compose.yml down
```

> To display the configuration:
> ```bash
> docker compose -f scraper/docker-compose.yml --env-file .env config
> ```


## ahoonepi' proxies

All ahoonepi' proxies have a `admin` user with sudo rights. All have a different password for this user.

They all connect by `autossh` (reverse tunnel) towards the `proxypi` user of the lighthouse. 
*This dummy user does not have any rights, neither to write, read or execute beyond its `.ssh` folder.*

However, all proxies are accessible **from any user of the lighthouse** through an opened port on `admin@localhost`.

The number of the opened port is decided by concatenate the prefix `22` and the proxy's ID (from `02` to `99`, `00` and `01` referring to the lighthouse).


## To format the python code

```bash
docker compose -f tests/docker-compose.yml --env-file .env up --build -d
docker logs tests
```

```bash
python -m venv ~/py_envs
source ~/py_envs/bin/activate
python -m venv ~/py_envs
black *
```
