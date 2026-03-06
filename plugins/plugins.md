Plugins are the pieces of code that may be used by multiple docker services.

So far it includes the Broker and the Scraper.

# ghost folder

The problem is that :
- we have /broker, /scraper and /plugins at the root of the project,
- and we launch them from there (docker compose -f scraper/docker-compose.yml --env-file .env up --build -d)
- and the context inside the dockerfiles is limited to their folders (ie context: .)

This is due to Nginx Proxy Manager having restrictions. So the context cannont extend.

A solution would be to have all the docker services in a separate folder.

But instead, we just mount the plugins directory to the root of the container and not inside the app folder.

If we mount the plugins directory inside the app mounting point, an empty plugins folder is created on the host.

(see /plugins/fast_api_ip_middleware.py for more info)

# __pycache__ folder

I think the problem is kinda the same with a __pycache__ folder being created on the host.

But it is less of an issue, it is easily tracked by the .gitignore contrary to the plugins folder.

# Unexpected crash at build on "unknown module fast_api_ip_middleware"

Solved by keeping the uvicorn command separated in a shell script, launched itself by the Dockerfile.

I have no fucking idea of how it is related.
