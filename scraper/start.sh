#!/bin/bash

Xvfb :99 -screen 0 1920x1080x24 > /dev/null 2>&1 &
sleep 2

exec uvicorn main:app --host 0.0.0.0 --port 8000 --reload
