FROM python:3.14-slim

WORKDIR /app

RUN pip install --no-cache-dir flask gunicorn

COPY . .

EXPOSE 8910

CMD ["gunicorn", "-b", "0.0.0.0:8910", "-w", "1", "--timeout", "30", "server:app"]
