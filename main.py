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
import matchMakingAlgorithm


app = FastAPI()


AWS_REGION = "us-east-1"  # Replace with your preferred AWS region
os.environ['AWS_DEFAULT_REGION'] = AWS_REGION

# Initialize DynamoDB client

dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)

tableChat = dynamodb.Table('ChatMessages')
tableProfile = dynamodb.Table('UserProfiles')

# Hardcoded admin ID

adminid = 'ef5490d5-e978-4d3e-9596-ba0f667b698e'


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


def get_user_from_id(user_id: str) -> Optional[str]:
    try:
        conn = http.client.HTTPSConnection("api.heartbeat.chat")
        headers = {
            'authorization': 'Bearer hb:76bffd9b05b2539c4d9d0960e825d2dd34bcaba31c32e0058e',
            'content-type': 'application/json'
        }
        conn.request("GET", f"/v0/users/{user_id}", headers=headers)
        res = conn.getresponse()
        data = res.read()

        user = json.loads(data.decode("utf-8"))
        return user

    except Exception as e:
        print(f"Error fetching user: {e}")
        return None

def check_if_channel_category_exists(name: str):
    try:
        conn = http.client.HTTPSConnection("api.heartbeat.chat")
        headers = {
            'authorization': 'Bearer hb:76bffd9b05b2539c4d9d0960e825d2dd34bcaba31c32e0058e',
            'accept': 'application/json'
        }
        conn.request("GET", "/v0/channelCategories", headers=headers)
        res = conn.getresponse()
        data = res.read()

        channel_categories = json.loads(data.decode("utf-8"))

        for category in channel_categories:
            if category['name'] == name:
                return category['id']

        return None

    except Exception as e:
        print(f"Error fetching channel categories: {e}")
        return None



def get_ai_response(user_message: str) -> Optional[str]:
    try:
        conn = http.client.HTTPConnection("54.161.37.146")
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
            return response_json
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

        user_email = get_user_from_id(sender_user_id).get('email')
        recent_messages = get_recent_messages(chat_id)

        if recent_messages and 'content' in recent_messages[-1]:
            latest_message_content = recent_messages[-1]['content'].strip().lower()
            clean_message_content = strip_html_tags(latest_message_content)
            print(f"Latest message content (cleaned): {clean_message_content}")

            store_message_in_dynamodb(chat_id, chat_message_id, clean_message_content, sender_user_id)

            if clean_message_content == "i want to get matched":
                send_direct_message(sender_user_id, adminid, "Finding a match for you... May take a few seconds.")
                res = matchMakingAlgorithm.run_matchmaking_algorithm(sender_user_id, tableProfile)

                matched_user_id = res.get('top_match')
                print(f"Matched user ID: {matched_user_id}")
                                
                channel_category_id = check_if_channel_category_exists("Matches")

                # If the category doesn't exist, create it
                if not channel_category_id:
                    channel_category_id = create_channel_category("Matches")

                if channel_category_id:
                    create_chat_channel(channel_category_id, sender_user_id)
                    print(f"Match channel created for user {sender_user_id} in category {channel_category_id}.")
                else:
                    print("Failed to create channel category for matches.")
                
                return True
            
            ai_response = get_ai_response(clean_message_content)
            if ai_response:
                send_direct_message(sender_user_id, adminid, ai_response['assistant_response'])
                store_message_in_dynamodb(chat_id, generate_message_id(), ai_response, adminid)
                store_user_profile_in_dynamodb(sender_user_id, ai_response['user_profile'])

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
        tableChat.put_item(
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


def store_user_profile_in_dynamodb(user_id: str, user_profile: dict):
    try:
        tableProfile.put_item(
            Item={
                'UserID': user_id,
                'UserProfile': user_profile
            }
        )
        print(f"Stored user profile in DynamoDB: UserID={user_id}")
    except Exception as e:
        print(f"Error storing user profile in DynamoDB: {e}")



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
            'authorization': 'Bearer hb:76bffd9b05b2539c4d9d0960e825d2dd34bcaba31c32e0058e',
            'content-type': 'application/json'
        }

        conn.request("PUT", "/v0/directMessages", payload, headers)
        res = conn.getresponse()
        data = res.read()

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
            'authorization': 'Bearer hb:76bffd9b05b2539c4d9d0960e825d2dd34bcaba31c32e0058e',
            'accept': 'application/json'
        }

        conn.request("GET", f"/v0/directMessages/{chat_id}", headers=headers)
        res = conn.getresponse()
        data = res.read()

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
            'authorization': 'Bearer hb:76bffd9b05b2539c4d9d0960e825d2dd34bcaba31c32e0058e',
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


def create_chat_channel(channel_category_id: str, sender_user_id: str) -> Optional[str]:
    try:
        user_email = get_user_from_id(sender_user_id).get('email')
        admin_email = get_user_from_id(adminid).get('email')

        conn = http.client.HTTPSConnection("api.heartbeat.chat")
        payload = json.dumps({
            "isPrivate": True,
            "channelCategoryID": channel_category_id,
            "name": "Chat with Fony Stark",
            "description": "A private channel for your match.",
            "invitedUsers": [
                user_email,
                admin_email
            ],
            "channelType": "CHAT"
        })
        headers = {
            'authorization': 'Bearer hb:76bffd9b05b2539c4d9d0960e825d2dd34bcaba31c32e0058e',
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