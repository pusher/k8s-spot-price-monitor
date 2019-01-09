FROM python:3.6-alpine

COPY spot_price_monitor/spot_price_monitor.py /
COPY requirements.txt /

RUN apk add --no-cache --virtual build-dependencies gcc musl-dev && \
    pip install --no-cache-dir -r /requirements.txt && \
    apk del build-dependencies

ENTRYPOINT ["python", "-u", "spot_price_monitor.py"]
