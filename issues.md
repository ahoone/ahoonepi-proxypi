- scraping work just sometimes on the initialization of a browser
- usually i remove the container and then rebuilt it
- but apparently using a different id is working
```
admin@ahoonepi:~ $ curl -X POST "http://10.0.0.3:8000/scrape?url=https://boutique.magiccorporation.com/produit-38669-lorwyn-eclipse-montagne-a4-9-pocket-zippered-pro-binder-360-cartes-recto-verso.html"
{"detail":"Exception at line 229: \n                ---------------------\n                Failed to connect to browser\n                ---------------------\n                One of the causes could be when you are running as root.\n                In that case you need to pass no_sandbox=True \n                "}admin@ahoonepi:~ $ curl -X POST "http://10.0.0.3:8000/scrape?url=https://boutique.magiccorporation.com/produit-38669-lorwyn-e
admin@ahoonepi:~ $ 
admin@ahoonepi:~ $ curl -X POST "http://10.0.0.3:8000/scrape?url=https://boutique.magiccorporation.com/produit-38669-lorwyn-eclipse-montagne-a4-9-pocket-zippered-pro-binder-360-cartes-recto-verso.html&instance_id=test"
{"status":"success"...
```
- Here is the working fix : a specific retry should be implemented for the scraper component
```
INFO:     172.28.0.1:34736 - "POST /new_instance HTTP/1.1" 200 OK
INFO:     172.28.0.1:51764 - "POST /new_instance HTTP/1.1" 200 OK
INFO:     172.28.0.1:51768 - "POST /kill HTTP/1.1" 200 OK
INFO:     172.28.0.1:51778 - "GET /browser_stats HTTP/1.1" 200 OK
WARNING:  Invalid HTTP request received.
WARNING:  Invalid HTTP request received.
admin@ahoonepi:~ $ docker restart scraper-fastapi-1 
scraper-fastapi-1
admin@ahoonepi:~ $ python3 test.py 
Failed with status 500: {'detail': 'Exception at line 230: \n                ---------------------\n                Failed to connect to browser\n                ---------------------\n                One of the causes could be when you are running as root.\n                In that case you need to pass no_sandbox=True \n                '}
Failed with status 500: {'detail': 'Exception at line 230: \n                ---------------------\n                Failed to connect to browser\n                ---------------------\n                One of the causes could be when you are running as root.\n                In that case you need to pass no_sandbox=True \n                '}
Failed with status 409: {'detail': 'No browser instance with id test'}
admin@ahoonepi:~ $ docker restart scraper-fastapi-1 
scraper-fastapi-1
admin@ahoonepi:~ $ docker ps
CONTAINER ID   IMAGE                             COMMAND                  CREATED        STATUS          PORTS                                                                                      NAMES
ccf0b2c2d261   scraper-fastapi                   "/app/start.sh"          8 days ago     Up 53 seconds   0.0.0.0:8000->8000/tcp, [::]:8000->8000/tcp                                                scraper-fastapi-1
e5a1671b3632   broker-fastapi                    "/app/start.sh"          13 days ago    Up 2 minutes    0.0.0.0:8080->8000/tcp, [::]:8080->8000/tcp                                                broker-fastapi-1
7d17686dee00   jc21/nginx-proxy-manager:latest   "/init"                  2 weeks ago    Up 2 weeks      0.0.0.0:80-81->80-81/tcp, [::]:80-81->80-81/tcp, 0.0.0.0:443->443/tcp, [::]:443->443/tcp   nginx-proxy-manager
8f1c1260ce4c   58b928712463                      "/docker-entrypoint.…"   2 months ago   Up 2 weeks      80/tcp                                                                                     scrapmagic-frontend
admin@ahoonepi:~ $ docker stop scraper-fastapi-1 
scraper-fastapi-1
admin@ahoonepi:~ $ docker rm scraper-fastapi-1 
scraper-fastapi-1
admin@ahoonepi:~ $ docker compose -f scraper/docker-compose.yml --env-file .env up --build -d
[+] Building 1.5s (17/17) FINISHED                                                                                                                                                                                 
 => [internal] load local bake definitions                                                                                                                                                                    0.0s
 => => reading from stdin 494B                                                                                                                                                                                0.0s
 => [internal] load build definition from Dockerfile                                                                                                                                                          0.0s
 => => transferring dockerfile: 2.19kB                                                                                                                                                                        0.0s
 => [internal] load metadata for docker.io/library/python:3.10-slim                                                                                                                                           0.8s
 => [internal] load .dockerignore                                                                                                                                                                             0.0s
 => => transferring context: 2B                                                                                                                                                                               0.0s
 => [ 1/10] FROM docker.io/library/python:3.10-slim@sha256:4ba18b066cee17f2696cf9a2ba564d7d5eb05a91d6a949326780aa7c6912160d                                                                                   0.0s
 => => resolve docker.io/library/python:3.10-slim@sha256:4ba18b066cee17f2696cf9a2ba564d7d5eb05a91d6a949326780aa7c6912160d                                                                                     0.0s
 => [internal] load build context                                                                                                                                                                             0.0s
 => => transferring context: 20.96kB                                                                                                                                                                          0.0s
 => CACHED [ 2/10] RUN apt-get update && apt-get install -y     net-tools ffmpeg     wget gnupg xvfb ca-certificates     fonts-liberation libx11-xcb1 libxcomposite1     libxcursor1 libxdamage1 libxext6 li  0.0s
 => CACHED [ 3/10] RUN ARCH=$(dpkg --print-architecture)     && if [ "$ARCH" = "amd64" ]; then         wget -q -O /tmp/google-chrome-stable_current_amd64.deb             https://dl.google.com/linux/direct  0.0s
 => CACHED [ 4/10] WORKDIR /app                                                                                                                                                                               0.0s
 => CACHED [ 5/10] COPY requirements.txt /app/requirements.txt                                                                                                                                                0.0s
 => CACHED [ 6/10] RUN pip install --no-cache-dir -r /app/requirements.txt                                                                                                                                    0.0s
 => [ 7/10] COPY . /app/                                                                                                                                                                                      0.0s
 => [ 8/10] RUN chmod +x /app/start.sh                                                                                                                                                                        0.2s
 => [ 9/10] RUN groupadd -r chrome && useradd -r -g chrome -m chrome                                                                                                                                          0.3s
 => [10/10] COPY --chown=chrome:chrome . /app                                                                                                                                                                 0.0s
 => exporting to image                                                                                                                                                                                        0.1s
 => => exporting layers                                                                                                                                                                                       0.0s
 => => writing image sha256:e6a2e1b0c23cad31c0d94dd4080bff64afb2645e44ae5ddbb9c7e8081ea091e9                                                                                                                  0.0s
 => => naming to docker.io/library/scraper-fastapi                                                                                                                                                            0.0s
 => resolving provenance for metadata file                                                                                                                                                                    0.0s
[+] up 3/3
 ✔ Image scraper-fastapi       Built                                                                                                                                                                           1.6s
 ✔ Container scraper-fastapi-1 Started                                                                                                                                                                         0.2s
 ! fastapi                     Your kernel does not support memory soft limit capabilities or the cgroup is not mounted. Limitation discarded.                                                                 0.0s
admin@ahoonepi:~ $ docker ps
CONTAINER ID   IMAGE                             COMMAND                  CREATED         STATUS         PORTS                                                                                      NAMES
b6f0706b1f95   scraper-fastapi                   "/app/start.sh"          5 seconds ago   Up 4 seconds   0.0.0.0:8000->8000/tcp, [::]:8000->8000/tcp                                                scraper-fastapi-1
e5a1671b3632   broker-fastapi                    "/app/start.sh"          13 days ago     Up 2 minutes   0.0.0.0:8080->8000/tcp, [::]:8080->8000/tcp                                                broker-fastapi-1
7d17686dee00   jc21/nginx-proxy-manager:latest   "/init"                  2 weeks ago     Up 2 weeks     0.0.0.0:80-81->80-81/tcp, [::]:80-81->80-81/tcp, 0.0.0.0:443->443/tcp, [::]:443->443/tcp   nginx-proxy-manager
8f1c1260ce4c   58b928712463                      "/docker-entrypoint.…"   2 months ago    Up 2 weeks     80/tcp                                                                                     scrapmagic-frontend
admin@ahoonepi:~ $ python3 test.py 
Success with status 200: None
Success with status 200: None
Success with status 200: None
```



- Negative latency for sequential commands in swarm execute
- Admin user retrieved instead of status

```
admin@ahoonepi:~ $ proxypi --swarm-execute 20 "whoami; whoami"
HOSTNAME                │PORT    │COMMAND STATUS    │COMMAND LATENCY (ms)    
────────────────────────┼────────┼──────────────────┼────────────────────────
ahoonepi-proxy-2        │2202    │admin             │-1771719731129          
ahoonepi-proxy-14       │2214    │admin             │-1771719731130          
ahoonepi-proxy-3        │2203    │admin             │-1771719731132          
```


- Function apt-update not working properly

```
admin@ahoonepi:~ $ proxypi apt-update 
HOSTNAME                │PORT    │UP TO DATE              
────────────────────────┼────────┼────────────────────────
ahoonepi (lighthouse)   │        │✓ Up to date.           
ahoonepi-proxy-14       │2214    │✓ Up to date.           
ahoonepi-proxy-2        │2202    │✓ Up to date.           
ahoonepi-proxy-3        │2203    │✓ Up to date.           
admin@ahoonepi:~ $ sudo apt update
Hit:1 http://deb.debian.org/debian trixie InRelease
Hit:2 http://deb.debian.org/debian trixie-updates InRelease      
Hit:3 http://deb.debian.org/debian-security trixie-security InRelease
Hit:4 http://archive.raspberrypi.com/debian trixie InRelease     
3 packages can be upgraded. Run 'apt list --upgradable' to see them.
```

- If you run the docker initialization script with the proxypi swarm method, be aware that `bash` and `./` are **not** equivalent:

```
xxx@ahoonepi:~ $ proxypi --swarm-execute 120 "sudo bash /ahoonepi-proxy/init_docker.sh"
┌─────────────────────────────────────────────────────────────────────────────┒
│HOSTNAME                │PORT    │COMMAND STATUS    │COMMAND LATENCY (ms)    ┃
│────────────────────────┼────────┼──────────────────┼────────────────────────┃
│ahoonepi-proxy-14       │2214    │✗ Failed.         │10                      ┃
│ahoonepi-proxy-3        │2203    │✗ Failed.         │9                       ┃
│ahoonepi-proxy-2        │2202    │✗ Failed.         │9                       ┃
┕━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
xxx@ahoonepi:~ $ proxypi --swarm-execute 120 "sudo ./ahoonepi-proxy/init_docker.sh"
┌─────────────────────────────────────────────────────────────────────────────┒
│HOSTNAME                │PORT    │COMMAND STATUS    │COMMAND LATENCY (ms)    ┃
│────────────────────────┼────────┼──────────────────┼────────────────────────┃
│ahoonepi-proxy-3        │2203    │✓ Success.        │7690                    ┃
│ahoonepi-proxy-14       │2214    │✓ Success.        │7724                    ┃
│ahoonepi-proxy-2        │2202    │✓ Success.        │7757                    ┃
┕━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
```

another problem with swarm execute on `;;`
```
admin@ahoonepi:~ $ proxypi swarm-execute 120 "cd ahoonepi-proxypi;; echo NODE_ROLE=PROXY,SCRAPER\nLIGHTHOUSE_IP=ahoonepi.fr > .env"
HOSTNAME                │PORT    │COMMAND STATUS    │COMMAND LATENCY (ms)    
────────────────────────┼────────┼──────────────────┼────────────────────────
                        │2202    │                  │0                       
                        │2203    │                  │0                       
                        │2214    │                  │0                       
```
AND NO FUCKING IDEA OF WHY THE ECHO > IS NOT WORKING TROUGH SWARM-EXECUTE
