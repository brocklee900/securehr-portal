#!/bin/sh
set -eu
touch /var/log/securehr/employee-search.log
chmod 644 /var/log/securehr/employee-search.log
crond
