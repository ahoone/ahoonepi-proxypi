# ahoonepi-proxypi

ahoonepi-proxypi provides an infrastructure to control multiple computers using its bash command line library (proxypi),
and providing an automated scraping setup for the network (ahoonepi).
It relies on [zendriver](https://github.com/cdpdriver/zendriver) (following [nodriver](https://github.com/ultrafunkamsterdam/nodriver/) abandon), provides chrome or chromium instances with a virtual display via Xvfb,
all of it inside of containers, and allocates scraping requests to stay undetected.

## Usage

Be aware that the project runs for now with high control:
- runs with sudo rights,
- docker commmand line without sudo,
- creates a dummy user,
- preferably on a fresh installed OS,

Start the project on the main computer that will be the lighthouse.
Create a `.env` and launch `./init.sh` (handles dependencies, ie docker and wireguard).
After rebooting, check that a `broker` container is running.
You should be able to access http://localhost:8080/ (or `HTTP_PORT_BROKER` from `config.env`).

To pursue the installation of proxies, creates an `admin` user (defined in `proxypi.sh`).
Complete the `.env` with the information you need from the lighthouse.
Be aware that the `PROXY_ID` should be unique among your network, and should be between 2 and 254 included.
On the lighthouse, run `proxypi load-ssh` and `proxypi load-wireguard`.
You should now see the proxy appear on the dashboard.

#### `.env`

```
LIGHTHOUSE_IP=
LIGHTHOUSE_SSH_PORT=
LIGHTHOUSE_WIREGUARD_PUBLIC_KEY=
NODE_ROLE=  # LIGHTHOUSE, PROXY, SCRAPER
PROXY_ID=
```

## For merge requests

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
