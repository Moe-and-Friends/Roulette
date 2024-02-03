FROM python:3.11.7-alpine

LABEL maintainer=Kyrielight

RUN apk update
RUN apk add git

COPY requirements.txt /opt/requirements.txt
RUN pip install -r /opt/requirements.txt && rm /opt/requirements.txt

COPY *.py /roulette/
COPY intervals/*.py /roulette/intervals/

WORKDIR /roulette
ENTRYPOINT ["python3", "main.py"]