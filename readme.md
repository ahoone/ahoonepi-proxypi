# ahoonepi-proxypi

ahoonepi-proxypi provides an infrastructure to control multiple computers using its bash command line library (proxypi),
and providing an automated scraping setup for the network (ahoonepi).
It relies on [zendriver](https://github.com/cdpdriver/zendriver) (following [nodriver](https://github.com/ultrafunkamsterdam/nodriver/) abandon), provides chrome or chromium instances with a virtual display via Xvfb,
all of it inside of containers, and allocates scraping requests to stay undetected.

# Usage



## Initialization


#### `.env`

```bash
GIT_BRANCH=
GIT_HOSTING_PROVIDER=
GIT_REPOSITORY=
LIGHTHOUSE_DUMMY_USER=
LIGHTHOUSE_IP=
LIGHTHOUSE_SSH_PORT=
LIGHTHOUSE_WIREGUARD_PUBLIC_KEY=
NODE_ROLE=
PROXY_ID=
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
docker compose -f scraper/docker-compose.yml --env-file .env --env-file config.env up --build -d
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
docker compose -f tests/docker-compose.yml --env-file config.env up --build -d
docker logs tests
```

```bash
python -m venv ~/py_envs
source ~/py_envs/bin/activate
python -m venv ~/py_envs
black .
```
