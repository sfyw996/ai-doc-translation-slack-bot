import os
from datetime import datetime, timedelta
import pytz
from typing import Optional

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- Configuration ---
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ORIGINAL_CHANNEL_ID = os.getenv("ORIGINAL_CHANNEL_ID")
TRANSLATED_CHANNEL_ID = os.getenv("TRANSLATED_CHANNEL_ID")

# --- Client Initialization ---
slack_client = WebClient(token=SLACK_BOT_TOKEN)
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('models/gemini-1.5-flash')

def get_messages_from_slack(channel_id: str, oldest_timestamp: str, latest_timestamp: str) -> list:
    """Fetches messages from a Slack channel within a time range."""
    messages = []
    try:
        response = slack_client.conversations_history(
            channel=channel_id,
            oldest=oldest_timestamp,
            latest=latest_timestamp, # Use the provided latest_timestamp
            limit=100
        )
        messages = response["messages"]
        # TODO: Implement pagination if more than 100 messages are expected
    except SlackApiError as e:
        print(f"Error fetching Slack messages: {e.response['error']}")
    return messages

def translate_text_with_gemini(text: str) -> Optional[str]:
    """Translates text into Japanese using the Gemini API."""
    if not text.strip():
        return ""
    try:
        prompt = f"以下のテキストを日本語に翻訳してください。:\n\n{text}"
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Error translating text with Gemini: {e}")
        return None

def post_message_to_slack(channel_id: str, text: str):
    """Posts a message to a Slack channel."""
    try:
        slack_client.chat_postMessage(channel=channel_id, text=text)
        print(f"Message posted to {channel_id}")
    except SlackApiError as e:
        print(f"Error posting message to Slack: {e.response['error']}")

def main():
    """Orchestrates fetching, translating, and posting Slack messages."""
    print("Starting Slack translation bot...")

    tz = pytz.timezone('Asia/Tokyo') # Set timezone to JST

    # Calculate timestamps for the last 24 hours relative to now
    # Slack API typically expects Unix timestamps (UTC).
    # Get current time in JST, then convert to UTC for Slack API.
    now_jst = datetime.now(tz)
    
    # The end of the period is 'now'
    end_time_utc = now_jst.astimezone(pytz.utc)
    # The start of the period is 24 hours before 'now'
    start_time_utc = (now_jst - timedelta(hours=24)).astimezone(pytz.utc)

    # Convert to Unix timestamps (strings) for Slack API
    oldest_ts = str(start_time_utc.timestamp())
    latest_ts = str(end_time_utc.timestamp())

    print(f"Processing period: {start_time_utc.strftime('%Y-%m-%d %H:%M:%S UTC')} to {end_time_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}")

    # Fetch messages from the original channel
    messages_to_translate = get_messages_from_slack(ORIGINAL_CHANNEL_ID, oldest_ts, latest_ts)
    print(f"Number of messages retrieved: {len(messages_to_translate)}")

    # Process messages (reversed to post oldest first)
    for message in reversed(messages_to_translate):
        # Filter out bot messages and non-standard message types
        if 'text' in message and not message.get('bot_id') and not message.get('subtype'):
            original_text = message['text']
            print(f"Original message (first 50 chars): {original_text[:50]}...")

            translated_text = translate_text_with_gemini(original_text)

            if translated_text:
                user_id = message.get('user', 'unknown_user_id')
                # Convert Slack's Unix timestamp (which is UTC) to JST for display
                posted_at_jst = datetime.fromtimestamp(float(message['ts']), tz=pytz.utc).astimezone(tz).strftime('%Y-%m-%d %H:%M:%S JST')

                formatted_message = (
                    f"--- Translated AI-related Post ---\n"
                    f"Original:\n```{original_text}```\n\n"
                    f"Translation:\n```{translated_text}```\n"
                    f"(_Original poster: <@{user_id}>, Posted at: {posted_at_jst}_)"
                )
                post_message_to_slack(TRANSLATED_CHANNEL_ID, formatted_message)
            else:
                print(f"Translation failed for: {original_text[:50]}...")

    print("Slack translation bot execution finished.")

if __name__ == "__main__":
    main()