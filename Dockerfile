FROM python:3-alpine

COPY spot-price-monitor.py /
COPY requirements.txt /

RUN pip install -r /requirements.txt

ENTRYPOINT ["python", "-u", "spot-price-monitor.py"]
