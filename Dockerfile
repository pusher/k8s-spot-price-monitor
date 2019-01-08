FROM python:3.6-slim

COPY spot_price_monitor/spot_price_monitor.py /
COPY requirements.txt /

RUN pip install -r /requirements.txt

ENTRYPOINT ["python", "-u", "spot_price_monitor.py"]
