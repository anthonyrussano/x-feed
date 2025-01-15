import feedparser
import random
import requests
import os
import json
import logging
from datetime import datetime
from requests_oauthlib import OAuth1Session
import vars

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/feed_bot.log'),
        logging.StreamHandler()
    ]
)

class RssTweetBot:
    def __init__(self):
        self.ollama_api_key = vars.OLLAMA_API_KEY
        
        # Initialize OAuth session for Twitter
        self.oauth = OAuth1Session(
            vars.OAUTH_CONSUMER_KEY,
            client_secret=vars.OAUTH_CONSUMER_SECRET,
            resource_owner_key=vars.OAUTH_ACCESS_TOKEN,
            resource_owner_secret=vars.OAUTH_ACCESS_TOKEN_SECRET
        )
        
        # Load posted articles history
        self.history_file = 'logs/posted_articles.json'
        self.posted_articles = self.load_history()

    def load_history(self):
        """Load history of posted articles."""
        if os.path.exists(self.history_file):
            with open(self.history_file, 'r') as f:
                return json.load(f)
        return []

    def save_history(self, article_url):
        """Save posted article to history."""
        self.posted_articles.append({
            'url': article_url,
            'date': datetime.now().isoformat()
        })
        
        # Ensure the logs directory exists
        os.makedirs('logs', exist_ok=True)
        
        with open(self.history_file, 'w') as f:
            json.dump(self.posted_articles, f, indent=2)

    def get_random_feed_url(self, file_path):
        """Read RSS feed URLs from file and select a random one."""
        with open(file_path, 'r') as f:
            feeds = f.read().splitlines()
            # Filter out empty lines and comments, then get only the URL part before '!'
            valid_feeds = []
            for line in feeds:
                if line and not line.startswith('#'):
                    url = line.split('!')[0].strip()
                    valid_feeds.append(url)
            return random.choice(valid_feeds)

    def get_latest_article(self, feed_url):
        """Get the latest article from the RSS feed."""
        feed = feedparser.parse(feed_url)
        if not feed.entries:
            raise Exception(f"No entries found in feed: {feed_url}")
        
        # Get first article that hasn't been posted
        for entry in feed.entries:
            if not any(post['url'] == entry.link for post in self.posted_articles):
                article = {
                    'title': entry.title,
                    'link': entry.link,
                    'description': entry.get('description', ''),
                    'content': entry.get('content', [{'value': ''}])[0]['value']
                }
                return article
                
        raise Exception(f"No new articles found in feed: {feed_url}")

    def generate_tweet(self, article):
        """Generate tweet using Ollama WebUI API."""
        response = requests.post(
            "http://localhost:3000/api/chat/completions",
            headers={
                "Authorization": f"Bearer {self.ollama_api_key}",
                "Content-Type": "application/json"
            },
            json={
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a social media expert who creates engaging tweets. Your tweets should be informative yet conversational. IMPORTANT: Replace any [URL] placeholder with the actual article URL in your response. The full article URL must be included in the tweet."
                    },
                    {
                        "role": "user",
                        "content": f"""Read this article and create an engaging tweet about it:
                        
                        Title: {article['title']}
                        Content: {article['description']} {article['content']}
                        URL: {article['link']}"""
                    }
                ],
                "model": "phi4:14b",
                "stream": False,
                "temperature": 0.7
            }
        )
        
        if response.status_code != 200:
            raise Exception(f"Ollama API error: {response.text}")
            
        tweet_text = response.json()['choices'][0]['message']['content'].strip()
        return tweet_text

    def post_tweet(self, tweet_text):
        """Post tweet to X (Twitter) using OAuth."""
        payload = {"text": tweet_text}
        
        response = self.oauth.post(
            "https://api.twitter.com/2/tweets",
            json=payload
        )
        
        if response.status_code != 201:
            raise Exception(f"Error posting tweet: {response.text}")
            
        return response.json()

def main():
    try:
        bot = RssTweetBot()
        
        # Get random RSS feed
        feed_url = bot.get_random_feed_url('rss_feeds.txt')
        logging.info(f"Selected feed: {feed_url}")
        
        # Get latest article
        article = bot.get_latest_article(feed_url)
        logging.info(f"Found article: {article['title']}")
        
        # Generate tweet
        tweet = bot.generate_tweet(article)
        logging.info(f"Generated tweet: {tweet}")
        
        # Ensure URL is in the tweet, add it if missing
        if article['link'] not in tweet:
            if '[URL]' in tweet:
                tweet = tweet.replace('[URL]', article['link'])
            else:
                tweet = f"{tweet.rstrip()} {article['link']}"
        
        # Post tweet
        response = bot.post_tweet(tweet)
        logging.info(f"Tweet posted successfully: {response}")
        
        # Save to history
        bot.save_history(article['link'])
        logging.info("Updated article history")
        
    except Exception as e:
        logging.error(f"Error: {str(e)}")
        raise e

if __name__ == "__main__":
    main()