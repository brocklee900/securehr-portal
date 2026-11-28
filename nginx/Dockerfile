FROM nginx:1.27-alpine
RUN apk add --no-cache logrotate && mkdir -p /var/log/securehr
COPY logrotate.conf /etc/logrotate.d/securehr
COPY 40-logrotate.sh /docker-entrypoint.d/40-logrotate.sh
RUN chmod 0644 /etc/logrotate.d/securehr \
    && chmod +x /docker-entrypoint.d/40-logrotate.sh \
    && printf '#!/bin/sh\n/usr/sbin/logrotate /etc/logrotate.d/securehr\n' > /etc/periodic/hourly/securehr-logrotate \
    && chmod +x /etc/periodic/hourly/securehr-logrotate
