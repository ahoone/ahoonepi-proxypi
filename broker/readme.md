# known issues

## Multiple browsers instances created for one task

When creating a new browser instance for a task, the broker may re-enter its browser selection task in its update loop while it did not have the notification that the browser it asked for had been created.
Therefore, it will re-select the same task and ask for a new browser instance to be created.
This cycle is usually not a problem, but it may increase the consumption on the proxies.
