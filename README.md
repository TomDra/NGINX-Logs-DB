# NGINX-Logs-DB

Store NGINX logs to a PostgreSQL database for easier use in dashboards and such

You point the script at you NGINX log output, specify the log format and run periodically.

## Features

- Efficient, as it will not parse previously parsed logs.
- Accounts for log rotation and will grab the tail of the previous log if missed.
- Premade script to easily run a cron job with venv.
- Creates its own logs so you can easily tell if something has gone wrong.

## Requirements

- Python 3.x
- Create virtual enviroment `python3 -m venv venv/`
- Install imports into the virtual enviroment `pip3 install -r requirements.txt`
- Create a `.env` file laid out:
```
# .env

# Database Details
DB_HOST=192.168.*.*
DB_PORT=5432
DB_NAME=NGINX_Logs
DB_USER=Username
DB_PASSWORD=Password

# Path glob for your nginx logs
LOG_FILE_PATTERN=/var/log/nginx/*.log

# Where to store state (Temporary File)
STATE_FILE=/var/tmp/nginx_parser_state.json

# loguru settings
LOGURU_LEVEL=INFO
LOG_FILE=/var/log/nginx_parser.log
```

## How to Use

Run the script (The better way):

`./run_nginx_parser.sh`

You can run the script directly with python:

`python3 main.py`

In my use case I have a cron job set to run the script every 10 minutes
