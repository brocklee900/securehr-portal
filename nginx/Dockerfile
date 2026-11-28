FROM nginx:1.27-alpine
RUN apk add --no-cache logrotate && mkdir -p /var/log/securehr
COPY logrotate.conf /etc/logrotate.d/securehr
# The sed below strips Windows line endings, in case the file was checked out on Windows without .gitattributes.
COPY 40-logrotate.sh /docker-entrypoint.d/40-logrotate.sh
RUN chmod 0644 /etc/logrotate.d/securehr \
    && sed -i 's/\r$//' /docker-entrypoint.d/40-logrotate.sh \
    && chmod +x /docker-entrypoint.d/40-logrotate.sh \
    && printf '#!/bin/sh\n/usr/sbin/logrotate /etc/logrotate.d/securehr\n' > /etc/periodic/hourly/securehr-logrotate \
    && chmod +x /etc/periodic/hourly/securehr-logrotate
