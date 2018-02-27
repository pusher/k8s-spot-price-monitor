FROM python:3-alpine

COPY docker-entrypoint.py /
COPY requirements.txt /

RUN pip install -r /requirements.txt

ENTRYPOINT ["python", "-u", "docker-entrypoint.py"]
