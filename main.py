import os
import glob
import json
import re
import hashlib
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import psycopg2
from loguru import logger

# ─ Configuration
load_dotenv()

DB_CFG = {
    "host":     os.getenv("DB_HOST"),
    "port":     os.getenv("DB_PORT", "5432"),
    "dbname":   os.getenv("DB_NAME"),
    "user":     os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
}
LOG_GLOB        = os.getenv("LOG_FILE_PATTERN", "/var/log/nginx/*.log")
STATE_FILE_PATH = Path(os.getenv("STATE_FILE", "/var/tmp/nginx_parser_state.json"))
LOGURU_LEVEL    = os.getenv("LOGURU_LEVEL", "INFO")
LOGURU_FILE     = os.getenv("LOG_FILE", "nginx_parser.log")

logger.remove()
logger.add(LOGURU_FILE, level=LOGURU_LEVEL, rotation="10 MB", retention="7 days", backtrace=True, diagnose=True)
logger.add(lambda msg: print(msg, end=""), level="ERROR")

# Regex for my custom nginx detailed format
LOG_PATTERN = re.compile(
    r'^\[(?P<time_local>[^\]]+)\]\s*\|\s*(?P<host>[^|]+)\s*\|\s*'
    r'(?P<remote_addr>[^|]+)\s*\|\s*(?P<remote_user>[^|]+)\s*\|\s*'
    r'"(?P<request>.*?)"\s*Status="(?P<status>\d+)"\s*'
    r'BodyBytesSent="(?P<body_bytes_sent>[\d-]+)"\s*'
    r'Referer="(?P<http_referer>[^"]*)"\s*'
    r'UserAgent="(?P<http_user_agent>[^"]*)"\s*'
    r'RequestTime="(?P<request_time>[\d\.\-]+)"\s*'
    r'UpstreamResponseTime="(?P<upstream_response_time>[\d\.\-]+)"\s*'
    r'GzipRatio="(?P<gzip_ratio>[\d\.\-]+)"'
)

# ─ DB and State Handling
def load_state():
    if STATE_FILE_PATH.exists():
        try:
            return json.loads(STATE_FILE_PATH.read_text())
        except Exception:
            logger.warning("Could not parse state file; starting fresh.")
    return {"inode": None, "offset": 0}

def save_state(state):
    STATE_FILE_PATH.write_text(json.dumps(state))

def get_db_conn():
    return psycopg2.connect(**DB_CFG)

def ensure_table_exists(conn):
    with conn.cursor() as cur:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS nginx_logs (
            id TEXT PRIMARY KEY,
            time_local TIMESTAMP,
            host TEXT,
            remote_addr TEXT,
            remote_user TEXT,
            request TEXT,
            status INT,
            body_bytes_sent BIGINT,
            http_referer TEXT,
            http_user_agent TEXT,
            request_time REAL,
            upstream_response_time REAL,
            gzip_ratio REAL
        )
        """)
    conn.commit()

# ─ Read file & log parsing
def file_inode(path):
    return path.stat().st_ino

def select_latest_log():
    files = glob.glob(LOG_GLOB)
    if not files:
        raise FileNotFoundError(f"No logs matching {LOG_GLOB}")
    return Path(max(files, key=lambda p: Path(p).stat().st_mtime))

def to_nullable_float(value):
    return float(value) if value and value != '-' else None

def to_nullable_int(value):
    return int(value) if value and value != '-' else None

def process_file(path, start_offset, conn):
    path = Path(path)
    with path.open("r", encoding="utf-8", errors="ignore") as f, conn.cursor() as cur:
        f.seek(start_offset)
        for line in f:
            line = line.strip()
            if not line:
                continue
            m = LOG_PATTERN.match(line)
            if not m:
                logger.error(f"Unmatched line: {line}")
                continue
            data = m.groupdict()
            # timestamp
            try:
                data['time_local'] = datetime.strptime(data['time_local'], "%d/%b/%Y:%H:%M:%S %z")
            except Exception:
                data['time_local'] = None
            # unique ID
            uid = hashlib.sha1(line.encode('utf-8')).hexdigest()
            data['id'] = uid
            # conversions
            data['status'] = to_nullable_int(data.get('status'))
            data['body_bytes_sent'] = to_nullable_int(data.get('body_bytes_sent')) or 0
            data['request_time'] = to_nullable_float(data.get('request_time')) or 0.0
            data['upstream_response_time'] = to_nullable_float(data.get('upstream_response_time')) or 0.0
            data['gzip_ratio'] = to_nullable_float(data.get('gzip_ratio')) or 0.0
            # empty strings to None
            for fld in ('remote_user','http_referer','http_user_agent','request'):
                if data.get(fld) == '-':
                    data[fld] = None
            cur.execute(
                """
                INSERT INTO nginx_logs (id, time_local, host, remote_addr, remote_user, request,
                                        status, body_bytes_sent, http_referer, http_user_agent,
                                        request_time, upstream_response_time, gzip_ratio)
                VALUES (%(id)s, %(time_local)s, %(host)s, %(remote_addr)s, %(remote_user)s, %(request)s,
                        %(status)s, %(body_bytes_sent)s, %(http_referer)s, %(http_user_agent)s,
                        %(request_time)s, %(upstream_response_time)s, %(gzip_ratio)s)
                ON CONFLICT (id) DO NOTHING
                """, data)
        new_offset = f.tell()
    conn.commit()
    return new_offset

# ─ Main
def main():
    state = load_state()
    conn = get_db_conn()
    ensure_table_exists(conn)

    latest = select_latest_log()
    cur_inode = file_inode(latest)

    # handle rotation
    if state["inode"] and state["inode"] != cur_inode:
        logger.info("Detected log rotation. Processing remaining lines in old file...")
        for p in glob.glob(LOG_GLOB):
            p = Path(p)
            if file_inode(p) == state["inode"]:
                state["offset"] = process_file(p, state["offset"], conn)
                break
        state["inode"] = cur_inode
        state["offset"] = 0

    if state["inode"] is None:
        state["inode"] = cur_inode

    state["offset"] = process_file(latest, state["offset"], conn)
    save_state(state)
    logger.info(f"Processed up to offset {state['offset']} in {latest}")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("Fatal error in nginx parser")
        raise

