FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/feed_bot ./feed_bot
COPY rss_feeds.txt .

CMD ["python", "-m", "feed_bot"]