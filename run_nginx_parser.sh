
#   This script is created to run the main.py nginx log parser on a cron job.


set -euo pipefail

# ─ Grabs PROJECT_DIR dynamically
# this makes the script work no matter where you move it
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${PROJECT_DIR}/venv"
SCRIPT="${PROJECT_DIR}/main.py"
LOGFILE="${PROJECT_DIR}/run_nginx_parser.log"

# ─ Activate venv 
if [[ ! -f "${VENV_DIR}/bin/activate" ]]; then
  echo "ERROR: Virtualenv not found at ${VENV_DIR}" >&2
  echo "→ Create it with: python3 -m venv ${VENV_DIR}" >&2
  exit 1
fi
source "${VENV_DIR}/bin/activate"

# ─ Run the parser
exec python "${SCRIPT}" >> "${LOGFILE}" 2>&1
