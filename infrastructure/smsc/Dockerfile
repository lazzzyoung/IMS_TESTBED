FROM python:3.12-slim

WORKDIR /app

COPY smsc_server.py /app/smsc_server.py

EXPOSE 5060/udp 5060/tcp

CMD ["python", "/app/smsc_server.py"]
