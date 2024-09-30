import json
from concurrent.futures import ThreadPoolExecutor
import openai
import os

# Load OpenAI API key from environment
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# Function to call OpenAI assistant with batch processing
def call_openai_assistant_batch(json_schema, all_messages_batch):
    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=all_messages_batch,
            response_format={
                "type": "json_schema",
                "json_schema": json_schema
            }
        )

        # Extract all responses
        assistant_responses = [choice.message.content for choice in response.choices]
        return assistant_responses
    except Exception as e:
        print(f"Error during OpenAI call: {e}")
        return None

# Function to fetch a single user profile from the database
def get_user_profile(user_id: str, tableProfile):
    try:
        response = tableProfile.get_item(
            Key={'UserID': user_id}
        )
        return response.get('Item')
    except Exception as e:
        print(f"Error fetching user profile: {e}")
        return None

# Function to fetch all user profiles from the database in a batch
def get_all_user_profiles(tableProfile):
    try:
        response = tableProfile.scan()
        return response["Items"]
    except Exception as e:
        print(f"Error fetching all user profiles: {e}")
        return None

# Optimized matchmaking function with batch API calls and parallel processing
def run_matchmaking_algorithm(user_id: str, tableProfile: any):
    # Matchmaking JSON schema
    json_schema = {
        "name": "matchmaking_score",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "compatibility_score": {"type": "integer"}
            },
            "required": ["compatibility_score"],
            "additionalProperties": False
        }
    }

    all_messages = [{
        "role": "system",
        "content": '''You're an expert matchmaker. You'll be given attributes from 2 different people's matchmaking profiles in JSON format, compare them and output a compatibility score (on a scale of 1 to 10).'''
    }]

    # Attribute weights
    weights = {
        "Relationship_Goals": 1,
        "Appearance": 0.8,
        "Location": 0.5,
        "Spirituality": 0.5,
        "Personality_Attributes": 0.7,
        "Age": 0.8,
        "Interests": 0.7,
        "Identity_and_Preference": 1,
        "Kids": 0.1,
        "Smoking": 0.1,
        "Pets": 0.1,
        "Career_Goals": 0.2,
        "Annual_Income": 0.2,
        "Willingness_to_Travel": 0.1,
        "Special_Requests": 0
    }

    # Fetch user profiles
    user = get_user_profile(user_id, tableProfile)
    all_users = get_all_user_profiles(tableProfile)

    if not user or not all_users:
        return {"error": "Failed to fetch user profiles"}

    # Function to process each user in parallel
    def process_other_user(other_user):
        if other_user['UserID'] == user_id:
            return None  # Skip self

        compatibility_score = 0
        all_messages_batch = []

        for attribute, weight in weights.items():
            content_dict = {
                "Person 1": user.get(attribute, "Not specified"),
                "Person 2": other_user.get(attribute, "Not specified")
            }

            # Add comparison request to batch
            all_messages_batch.append({
                "role": "user",
                "content": json.dumps(content_dict)
            })

        # Batch API call to OpenAI
        assistant_responses = call_openai_assistant_batch(json_schema, all_messages_batch)

        # Process responses for each attribute
        for response, attribute in zip(assistant_responses, weights.keys()):
            try:
                attribute_score = json.loads(response)["compatibility_score"]
                compatibility_score += attribute_score * weights[attribute]
            except (json.JSONDecodeError, KeyError):
                print(f"Error decoding response for attribute {attribute}")
                continue

        return other_user['UserID'], compatibility_score

    # Run matchmaking in parallel
    with ThreadPoolExecutor() as executor:
        results = executor.map(process_other_user, all_users)

    # Collect valid results
    compatibility_scores = dict(filter(None, results))

    # Find the top match
    if compatibility_scores:
        top_match = max(compatibility_scores.items(), key=lambda x: x[1])
    else:
        top_match = None

    return {
        "user": user,
        "compatibility_scores": compatibility_scores,
        "top_match": top_match
    }

# Example usage
# tableProfile should be the DynamoDB or any other database resource being passed here
# user_id is the ID of the user for whom matchmaking needs to be run
# run_matchmaking_algorithm(user_id, tableProfile)
