#!/bin/bash
set -eo pipefail
source /opt/ros/humble/setup.bash
source /ws/install/setup.bash
exec python3 -m rosout_ingest.node
