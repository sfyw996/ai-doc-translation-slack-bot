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
model = genai.GenerativeModel('models/gemini-2.0-flash') # Using the gemini-1.5-flash model

def get_messages_from_slack(channel_id: str, oldest_timestamp: str, latest_timestamp: str) -> list:
    """Fetches messages from a Slack channel within a time range."""
    messages = []
    try:
        response = slack_client.conversations_history(
            channel=channel_id,
            oldest=oldest_timestamp,
            latest=latest_timestamp,
            limit=100
        )
        messages = response["messages"]
    except SlackApiError as e:
        print(f"Error fetching Slack messages: {e.response['error']}")
    return messages

def translate_text_with_gemini(text: str) -> Optional[str]:
    """Translates text into Japanese using the Gemini API."""
    if not text.strip():
        return ""
    try:
        prompt = (
            f"Translate the following text into Japanese, preserving all Slack-specific formatting. "
            f"This includes bold (*text*), italics (_text_), strikethrough (~text~), "
            f"inline code (`code`), code blocks (```code```), "
            f"links (<url|text>), user mentions (<@U123456789>), "
            f"channel mentions (<#C123456789|channel-name>), and emoji shortcodes (:smiley:). "
            f"Ensure the original formatting characters are kept around the translated text. "
            f"Provide only the translated text, with no additional conversational phrases.\n\n{text}"
        )
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Error translating text with Gemini: {e}")
        return None

# MODIFIED: post_message_to_slack now accepts thread_ts and returns the posted message's timestamp
def post_message_to_slack(channel_id: str, text: str, thread_ts: Optional[str] = None) -> Optional[str]:
    """
    Posts a message to a Slack channel, optionally in a thread.
    Returns the timestamp of the posted message.
    """
    try:
        response = slack_client.chat_postMessage(
            channel=channel_id,
            text=text,
            thread_ts=thread_ts # This parameter makes it a reply in a thread
        )
        print(f"Message posted to {channel_id}" + (f" in thread {thread_ts}" if thread_ts else ""))
        return response.get('ts') # Return the timestamp of the newly posted message
    except SlackApiError as e:
        print(f"Error posting message to Slack: {e.response['error']}")
        return None

def get_message_permalink(channel_id: str, message_ts: str) -> Optional[str]:
    """Fetches the permalink for a specific Slack message."""
    try:
        response = slack_client.chat_getPermalink(
            channel=channel_id,
            message_ts=message_ts
        )
        return response.get('permalink')
    except SlackApiError as e:
        print(f"Error getting permalink: {e.response['error']}")
        return None

def main():
    print("Starting Slack translation bot...")

    tz = pytz.timezone('Asia/Tokyo')
    now_jst = datetime.now(tz)
    
    end_time_utc = now_jst.astimezone(pytz.utc)
    start_time_utc = (now_jst - timedelta(hours=24)).astimezone(pytz.utc)

    oldest_ts = str(start_time_utc.timestamp())
    latest_ts = str(end_time_utc.timestamp())

    print(f"Processing period: {start_time_utc.strftime('%Y-%m-%d %H:%M:%S UTC')} to {end_time_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}")

    messages_to_translate = get_messages_from_slack(ORIGINAL_CHANNEL_ID, oldest_ts, latest_ts)
    print(f"Number of messages retrieved: {len(messages_to_translate)}")

    for message in reversed(messages_to_translate):
        if 'text' in message and not message.get('bot_id') and not message.get('subtype'):
            original_text = message['text']
            message_ts = message['ts'] # Timestamp of the original message
            print(f"Original message (first 50 chars): {original_text[:50]}...")

            translated_text = translate_text_with_gemini(original_text)

            if translated_text:
                translated_message_ts = post_message_to_slack(TRANSLATED_CHANNEL_ID, translated_text)
                
                if translated_message_ts:
                    original_permalink = get_message_permalink(ORIGINAL_CHANNEL_ID, message_ts)
                    
                    if original_permalink:
                        thread_reply_text = f"Original post: {original_permalink}"
                        post_message_to_slack(TRANSLATED_CHANNEL_ID, thread_reply_text, thread_ts=translated_message_ts)
                    else:
                        post_message_to_slack(TRANSLATED_CHANNEL_ID, "Original post link not available.", thread_ts=translated_message_ts)
                else:
                    print(f"Failed to post translated message for: {original_text[:50]}...")
            else:
                print(f"Translation failed for: {original_text[:50]}...")

    print("Slack translation bot execution finished.")

if __name__ == "__main__":
    main()