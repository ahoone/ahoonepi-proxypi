# ahoonepi-proxypi

ahoonepi-proxypi provides an infrastructure to control multiple computers using its bash command line library (proxypi),
and providing an automated scraping setup for the network.
It relies on [zendriver](https://github.com/cdpdriver/zendriver) (following [nodriver](https://github.com/ultrafunkamsterdam/nodriver/) abandon), provides chrome or chromium instances with a virtual display via Xvfb, all of it inside of containers, and allocates scraping requests to stay undetected.

## Demo

<video controls width="700">
  <source src="demo.mp4" type="video/mp4">
</video>

```bash
git clone https://github.com/ahoone/ahoonepi-proxypi
cd ahoonepi-proxypi
echo "NODE_ROLE=LIGHTHOUSE,SCRAPER" > .env
./init.sh
sudo reboot
```

After rebooting:
```bash
cd ahoonepi-proxypi
source .bash_aliases
proxypi container-restart 1
xdg-open http://localhost:8080/
xdg-open http://localhost:8080/docs
```

## Usage

Be aware that the project runs for now with high control:
- runs with sudo rights,
- docker commmand line without sudo,
- creates a dummy user,
- preferably on a fresh installed OS.

Start the project on the main computer that will be the lighthouse.
Create a `.env` and complete just the `NODE_ROLE` field and launch `./init.sh` (handles dependencies, ie docker and wireguard).
After rebooting, check that a `broker` container is running.
You should be able to access the [dashboard](http://localhost:8080/) (or `HTTP_PORT_BROKER` if you changed the port from `config.env`) and the [API documentation](http://localhost:8080/docs).

To pursue the installation of proxies, creates an `admin` user (defined in `proxypi.sh`).
Complete the `.env` with the information you need from the lighthouse.
Be aware that the `PROXY_ID` should be unique among your network, and should be between 2 and 254 included.
On the lighthouse, run `proxypi load-ssh` and `proxypi load-wireguard`.
You should now see the proxy appear on the dashboard.

#### `.env`

```
LIGHTHOUSE_IP=  # Just required for the proxies
LIGHTHOUSE_SSH_PORT=  # Just required for the proxies
LIGHTHOUSE_WIREGUARD_PUBLIC_KEY=  # Just required for the proxies
NODE_ROLE=  # LIGHTHOUSE, PROXY, SCRAPER
PROXY_ID=  # Just required for the proxies
```
