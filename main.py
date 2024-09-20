import json
import re
import http.client
import boto3
from boto3.dynamodb.conditions import Key
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
import uuid
import os

app = FastAPI()

AWS_REGION = "us-east-1"  # Replace with your preferred AWS region
os.environ['AWS_DEFAULT_REGION'] = AWS_REGION

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
table = dynamodb.Table('ChatMessages')

# Hardcoded admin ID
adminid = 'c0f25c6d-8fb5-4e16-939f-f5d0a5e1a966'

# State variables
# Note: In a production environment, you'd want to use a database or cache for these
awaiting_email = False
awaiting_chat_confirmation = False
user_email = None
channel_category_id = None

class MessageRequest(BaseModel):
    senderUserID: str
    chatID: str
    chatMessageID: str

def is_admin(user_id: str) -> bool:
    return user_id == adminid

def strip_html_tags(text: str) -> str:
    return re.sub(r'<[^>]+>', '', text)

def get_ai_response(user_message: str) -> Optional[str]:
    try:
        conn = http.client.HTTPSConnection("http://54.161.37.146")
        payload = json.dumps({
            "user_message": user_message,
            "conversation_history": []  # Empty history for now
        })
        headers = {
            'Content-Type': 'application/json'
        }
        conn.request("POST", "/chat/", payload, headers)
        res = conn.getresponse()
        data = res.read()
        
        if res.status == 200:
            response_json = json.loads(data.decode("utf-8"))
            return response_json.get('assistant_response')
        else:
            print(f"Error calling AI matchmaker: HTTP {res.status}, Response: {data.decode('utf-8')}")
            return None
    except Exception as e:
        print(f"Error calling AI matchmaker: {e}")
        return None

def process_direct_message(sender_user_id: str, receiver_user_id: str, chat_id: str, chat_message_id: str) -> bool:
    global awaiting_email, awaiting_chat_confirmation, user_email, channel_category_id

    try:
        print(f"Processing message from {sender_user_id} to {receiver_user_id}")
        print(f"Chat ID: {chat_id}, Message ID: {chat_message_id}")

        recent_messages = get_recent_messages(chat_id)
        print(f"Recent messages: {recent_messages}")

        if recent_messages and 'content' in recent_messages[-1]:
            latest_message_content = recent_messages[-1]['content'].strip().lower()
            clean_message_content = strip_html_tags(latest_message_content)
            print(f"Latest message content (cleaned): {clean_message_content}")

            store_message_in_dynamodb(chat_id, chat_message_id, clean_message_content, sender_user_id)

            if clean_message_content == "i want to get matched":
                response_text = "You've been matched to Tony Stark! Check your matches."
                send_direct_message(sender_user_id, adminid, response_text)
                store_message_in_dynamodb(chat_id, generate_message_id(), response_text, adminid)

                channel_category_id = create_channel_category("Matches")
                if channel_category_id:
                    create_chat_channel(channel_category_id, "ananth@lumiopartners.com", sender_user_id)
                    print(f"Match channel created for user {sender_user_id} in category {channel_category_id}.")
                else:
                    print("Failed to create channel category for matches.")
                
                return True
            
            ai_response = get_ai_response(clean_message_content)
            if ai_response:
                send_direct_message(sender_user_id, adminid, ai_response)
                store_message_in_dynamodb(chat_id, generate_message_id(), ai_response, adminid)
                return True
            else:
                print("Failed to get AI response, falling back to default behavior")

        if awaiting_email:
            if recent_messages and 'content' in recent_messages[-1]:
                latest_message_content = recent_messages[-1]['content'].strip().lower()
                clean_message_content = strip_html_tags(latest_message_content)
                print(f"Latest message content (cleaned): {clean_message_content}")

                if "@" in clean_message_content:
                    user_email = clean_message_content
                    print(f"User email captured: {user_email}")

                    channel_category_id = create_channel_category(f"Matches for {user_email}")
                    print(f"Channel category created with ID: {channel_category_id}")

                    response_text = "Do you want to chat with the match?"
                    send_direct_message(sender_user_id, adminid, response_text)
                    store_message_in_dynamodb(chat_id, generate_message_id(), response_text, adminid)

                    awaiting_chat_confirmation = True
                    awaiting_email = False
                    return True
                else:
                    print("Invalid email format. Awaiting correct email.")
                    response_text = "Please provide a valid email."
                    send_direct_message(sender_user_id, adminid, response_text)
                    store_message_in_dynamodb(chat_id, generate_message_id(), response_text, adminid)
                    return True

        if awaiting_chat_confirmation:
            if recent_messages and 'content' in recent_messages[-1]:
                latest_message_content = recent_messages[-1]['content'].strip().lower()
                clean_message_content = strip_html_tags(latest_message_content)
                print(f"Latest message content (cleaned): {clean_message_content}")

                if clean_message_content == "yes":
                    create_chat_channel(channel_category_id, user_email, sender_user_id)
                    response_text = "Chat channel created!"
                    send_direct_message(sender_user_id, adminid, response_text)
                    store_message_in_dynamodb(chat_id, generate_message_id(), response_text, adminid)
                    awaiting_chat_confirmation = False
                    return True
                else:
                    response_text = "Okay, let me know if you change your mind."
                    send_direct_message(sender_user_id, adminid, response_text)
                    store_message_in_dynamodb(chat_id, generate_message_id(), response_text, adminid)
                    awaiting_chat_confirmation = False
                    return True

        default_message = 'I am a matchmaker. Give me information about you so I can match you. If you want to get matched, say: I want to get matched.'
        send_direct_message(sender_user_id, adminid, default_message)
        store_message_in_dynamodb(chat_id, generate_message_id(), default_message, adminid)
        return True

    except Exception as e:
        print(f"Error processing direct message: {e}")
        return False

def store_message_in_dynamodb(chat_id: str, message_id: str, message_content: str, sender_user_id: str):
    try:
        table.put_item(
            Item={
                'ChatID': chat_id,
                'MessageID': message_id,
                'MessageContent': message_content,
                'SenderUserID': sender_user_id
            }
        )
        print(f"Stored message in DynamoDB: ChatID={chat_id}, MessageID={message_id}, SenderUserID={sender_user_id}")
    except Exception as e:
        print(f"Error storing message in DynamoDB: {e}")

def send_direct_message(to_user: str, from_user: str, text: str) -> Optional[str]:
    try:
        print(f"Sending message from {from_user} to {to_user}")
        conn = http.client.HTTPSConnection("api.heartbeat.chat")
        payload = json.dumps({
            "from": from_user,
            "to": to_user,
            "text": format_text(text)
        })
        headers = {
            'authorization': 'Bearer hb:8d3bdd6fe027d6add8b292940a9724f775ead140132c1ddb77',
            'content-type': 'application/json'
        }
        conn.request("PUT", "/v0/directMessages", payload, headers)
        res = conn.getresponse()
        data = res.read()

        print(f"Send direct message response: {data.decode('utf-8')}")
        return data.decode("utf-8")

    except Exception as e:
        print(f"Error sending direct message: {e}")
        return None

def format_text(text: str) -> str:
    return "<p>" + text + "</p>"

def get_recent_messages(chat_id: str) -> list:
    try:
        conn = http.client.HTTPSConnection("api.heartbeat.chat")
        headers = {
            'authorization': 'Bearer hb:8d3bdd6fe027d6add8b292940a9724f775ead140132c1ddb77',
            'accept': 'application/json'
        }
        conn.request("GET", f"/v0/directMessages/{chat_id}", headers=headers)
        res = conn.getresponse()
        data = res.read()

        print(f"Get recent messages response: {data.decode('utf-8')}")
        messages = json.loads(data.decode("utf-8"))
        if isinstance(messages, list):
            return messages
        else:
            print(f"Unexpected response format: {messages}")
            return []

    except Exception as e:
        print(f"Error fetching recent messages: {e}")
        return []

def create_channel_category(name: str) -> Optional[str]:
    try:
        conn = http.client.HTTPSConnection("api.heartbeat.chat")
        payload = json.dumps({
            "name": name
        })
        headers = {
            'authorization': 'Bearer hb:8d3bdd6fe027d6add8b292940a9724f775ead140132c1ddb77',
            'content-type': 'application/json'
        }
        conn.request("PUT", "/v0/channelCategories", payload, headers)
        res = conn.getresponse()
        data = res.read()

        print(f"Create channel category response: {data.decode('utf-8')}")
        response_json = json.loads(data.decode("utf-8"))
        return response_json.get('id')

    except Exception as e:
        print(f"Error creating channel category: {e}")
        return None

def create_chat_channel(channel_category_id: str, user_email: str, sender_user_id: str) -> Optional[str]:
    try:
        conn = http.client.HTTPSConnection("api.heartbeat.chat")
        payload = json.dumps({
            "isPrivate": True,
            "channelCategoryID": channel_category_id,
            "name": "Chat with Tony Stark",
            "description": "A private channel for your match.",
            "invitedUsers": [
                user_email,
                "ananthmanya2@gmail.com",
                "contact@lumiopartners.com"
            ],
            "channelType": "CHAT"
        })
        headers = {
            'authorization': 'Bearer hb:8d3bdd6fe027d6add8b292940a9724f775ead140132c1ddb77',
            'content-type': 'application/json'
        }
        conn.request("PUT", "/v0/channels", payload, headers)
        res = conn.getresponse()
        data = res.read()

        print(f"Create chat channel response: {data.decode('utf-8')}")
        return data.decode("utf-8")

    except Exception as e:
        print(f"Error creating chat channel: {e}")
        return None

def generate_message_id() -> str:
    return str(uuid.uuid4())

@app.post("/process_message")
async def process_message(message: MessageRequest):
    try:
        success = process_direct_message(message.senderUserID, adminid, message.chatID, message.chatMessageID)

        if success:
            return {"success": True, "message": "Message processed successfully"}
        else:
            raise HTTPException(status_code=500, detail="Message processing failed")

    except Exception as e:
        print(f"Error in process_message: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    return {"message": "Hello World"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)