FROM telegraf:1.32-alpine

RUN apk add --no-cache bash curl jq

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV WPC_DATA_DIR=/var/lib/wpc-agent \
    WPC_SERVER_URL=http://control-api.wolfpackcloud-control.svc.cluster.local:8000 \
    WPC_METRICS_URL= \
    WPC_ROBOT_NAME= \
    WPC_ARCH= \
    WPC_PAIR_POLL_SEC=5 \
    WPC_PAIR_TIMEOUT_SEC=900

ENTRYPOINT ["/entrypoint.sh"]
