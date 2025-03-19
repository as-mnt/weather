FROM python:3.9-slim

WORKDIR /app
COPY . /app

RUN cd /app && pip install -r requirements.txt

CMD ["python", "-u", "app/mkweathergraphs-loop.py"]
