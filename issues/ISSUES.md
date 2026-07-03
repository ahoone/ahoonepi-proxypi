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
