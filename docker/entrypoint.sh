#!/bin/bash
# Start syslog (Fledge logs there) and Fledge, then follow the log in the foreground.
set -e
rsyslogd || true
"$FLEDGE_ROOT/bin/fledge" start
touch /var/log/syslog
exec tail -F /var/log/syslog
