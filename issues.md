- comeback of the fucking problem
- we are not running as root (check /health)
- possibly because the exe is spiking at instance boot (https://github.com/cdpdriver/zendriver/issues/104#issuecomment-2815658031)
- reinstalling python with prefix arch -arm64 (https://github.com/cdpdriver/zendriver/issues/104#issuecomment-2818967124)
- my guess is multiple instances launched at almost the same time
- the following try work shows that it is happening randomly
- it happened again after I rebuilt the container
```
============================= test session starts ==============================
platform linux -- Python 3.10.20, pytest-9.0.3, pluggy-1.6.0 -- /usr/local/bin/python3.10
cachedir: .pytest_cache
rootdir: /app
collecting ... collected 9 items

test_broker.py::test_broker_available PASSED                             [ 11%]
test_broker.py::test_broker_receive_scrape_request PASSED                [ 22%]
test_scraper.py::test_scraper_available PASSED                           [ 33%]
test_scraper.py::test_default_new_instance PASSED                        [ 44%]
test_scraper.py::test_explicit_new_instance FAILED                       [ 55%]
test_scraper.py::test_get_page_explicit_instance PASSED                  [ 66%]
test_scraper.py::test_get_page_default_instance PASSED                   [ 77%]
test_scraper.py::test_kill_default_instance PASSED                       [ 88%]
test_scraper.py::test_explicit_instance_dead PASSED                      [100%]

=================================== FAILURES ===================================
__________________________ test_explicit_new_instance __________________________

    def test_explicit_new_instance():
        url = f"http://{ADDRESS}/new-instance"
        payload = {
            "instance_id": EXPLICIT_NEW_INSTANCE_ID,
            "lifespan_in_seconds": EXPLICIT_NEW_INSTANCE_LIFESPAN,
            "window_size": EXPLICIT_NEW_INSTANCE_WINDOW_SIZE,
        }
        response = requests.post(url, json=payload, timeout=TIMEOUT_REQUESTS)
>       assert response.status_code == 201, response.content
E       AssertionError: b'{"detail":"Exception at line 556: \
E                         ---------------------\
E                         Failed to connect to browser\
E                         ---------------------\
E                         One of the causes could be when you are running as root.\
E                         In that case you need to pass no_sandbox=True\
E                         "}'
E       assert 500 == 201
E        +  where 500 = <Response [500]>.status_code

test_scraper.py:46: AssertionError
=========================== short test summary info ============================
FAILED test_scraper.py::test_explicit_new_instance - AssertionError: b'{"deta...
========================= 1 failed, 8 passed in 27.05s =========================


============================= test session starts ==============================
platform linux -- Python 3.10.20, pytest-9.0.3, pluggy-1.6.0 -- /usr/local/bin/python3.10
cachedir: .pytest_cache
rootdir: /app
collecting ... collected 9 items

test_broker.py::test_broker_available PASSED                             [ 11%]
test_broker.py::test_broker_receive_scrape_request PASSED                [ 22%]
test_scraper.py::test_scraper_available PASSED                           [ 33%]
test_scraper.py::test_default_new_instance PASSED                        [ 44%]
test_scraper.py::test_explicit_new_instance PASSED                       [ 55%]
test_scraper.py::test_get_page_explicit_instance PASSED                  [ 66%]
test_scraper.py::test_get_page_default_instance PASSED                   [ 77%]
test_scraper.py::test_kill_default_instance PASSED                       [ 88%]
test_scraper.py::test_explicit_instance_dead PASSED                      [100%]

============================== 9 passed in 54.98s ==============================
```

- for the tests, the explicit new instance does not start if we are streaming the default one at the same time
- solved by switching to zendriver

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
