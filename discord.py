import feedparser
import random
import requests
import os
import json
import logging
from datetime import datetime
import time
from discord_webhook import DiscordWebhook, DiscordEmbed
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

class RssDiscordBot:
    def __init__(self):
        self.webhook_url = vars.DISCORD_WEBHOOK_URL
        self.ollama_api_key = vars.OLLAMA_API_KEY
        
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
            # Filter out empty lines and comments
            valid_feeds = []
            for line in feeds:
                if line and not line.startswith('#'):
                    # Split on first whitespace and take only the URL part
                    url = line.split()[0].strip()
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
                    'content': entry.get('content', [{'value': ''}])[0]['value'],
                    'author': entry.get('author', 'Unknown Author'),
                    'published': entry.get('published', datetime.now().isoformat())
                }
                return article
                
        raise Exception(f"No new articles found in feed: {feed_url}")

    def generate_summary(self, article):
        """Generate article summary using Ollama WebUI API."""
        # Truncate content to reduce context length
        max_content_length = 500
        combined_content = (article['description'] + ' ' + article['content']).strip()
        truncated_content = combined_content[:max_content_length] + ('...' if len(combined_content) > max_content_length else '')
        
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
                        "content": (
                            "You are a friendly content curator. Create engaging, professional summaries. "
                            "Keep responses concise and precise, around 2-3 sentences. "
                            "Write in a natural, conversational tone that would be appropriate for a Discord channel."
                        )
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Title: {article['title']}\n"
                            f"Content: {truncated_content}")
                    }
                ],
                "model": "phi4:14b",
                "stream": False,
                "temperature": 0.7
            }
        )
        
        if response.status_code != 200:
            raise Exception(f"Ollama API error: {response.text}")
            
        summary = response.json()['choices'][0]['message']['content'].strip()
        return summary

    def post_to_discord(self, article, summary):
        """Post article to Discord using webhooks."""
        webhook = DiscordWebhook(url=self.webhook_url)
        
        # Create embed
        embed = DiscordEmbed(
            title=article['title'],
            description=summary,
            url=article['link'],
            color=0x7289DA  # Discord blurple color
        )
        
        # Add author and publication date
        embed.set_author(name=article['author'])
        embed.set_footer(text=f"Published: {article['published']}")
        
        # Add embed to webhook
        webhook.add_embed(embed)
        
        # Execute webhook
        response = webhook.execute()
        
        if not response:
            raise Exception("Error posting to Discord")
            
        return response

def main():
    try:
        bot = RssDiscordBot()
        interval = 3  # Post every hour
        
        while True:
            try:
                # Get random RSS feed
                feed_url = bot.get_random_feed_url('rss_feeds.txt')
                logging.info(f"Selected feed: {feed_url}")
                
                # Get latest article
                article = bot.get_latest_article(feed_url)
                logging.info(f"Found article: {article['title']}")
                
                # Generate summary
                summary = bot.generate_summary(article)
                logging.info(f"Generated summary: {summary}")
                
                # Post to Discord
                response = bot.post_to_discord(article, summary)
                logging.info("Posted to Discord successfully")
                
                # Save to history
                bot.save_history(article['link'])
                logging.info("Updated article history")
                
            except Exception as e:
                logging.error(f"Error in main loop: {str(e)}")
                # Continue to next iteration instead of crashing
                
            # Sleep for the specified interval
            logging.info(f"Sleeping for {interval} seconds...")
            time.sleep(interval)
            
    except KeyboardInterrupt:
        logging.info("Bot stopped by user")
    except Exception as e:
        logging.error(f"Fatal error: {str(e)}")
        raise e

if __name__ == "__main__":
    main()