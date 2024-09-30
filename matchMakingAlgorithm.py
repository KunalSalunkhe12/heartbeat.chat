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

# Function to generate dynamic weights using OpenAI API
def generate_dynamic_weights(user):
    # Create a message to send to OpenAI API
    prompt = f"Generate weights for the following user attributes based on user preferences:\n" \
             f"Relationship Goals: {user.get('Relationship_Goals')}\n" \
             f"Appearance: {user.get('Appearance')}\n" \
             f"Location: {user.get('Location')}\n" \
             f"Spirituality: {user.get('Spirituality')}\n" \
             f"Personality Attributes: {user.get('Personality_Attributes')}\n" \
             f"Age: {user.get('Age')}\n" \
             f"Interests: {user.get('Interests')}\n" \
             f"Identity and Preference: {user.get('Identity_and_Preference')}\n" \
             f"Kids: {user.get('Kids')}\n" \
             f"Smoking: {user.get('Smoking')}\n" \
             f"Pets: {user.get('Pets')}\n" \
             f"Career Goals: {user.get('Career_Goals')}\n" \
             f"Annual Income: {user.get('Annual_Income')}\n" \
             f"Willingness to Travel: {user.get('Willingness_to_Travel')}\n" \
             f"Special Requests: {user.get('Special_Requests')}\n" \
             f"Please output a JSON object with weights for each attribute, scaled between 0 and 1."

    all_messages_batch = [{
        "role": "system",
        "content": "You are an expert in matchmaking. Generate weights based on user profile attributes."
    }, {
        "role": "user",
        "content": prompt
    }]

    json_schema = {
        "name": "weights",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "relationship_goals": {"type": "number"},
                "appearance": {"type": "number"},
                "location": {"type": "number"},
                "spirituality": {"type": "number"},
                "personality_attributes": {"type": "number"},
                "age": {"type": "number"},
                "interests": {"type": "number"},
                "identity_and_preference": {"type": "number"},
                "kids": {"type": "number"},
                "smoking": {"type": "number"},
                "pets": {"type": "number"},
                "career_goals": {"type": "number"},
                "annual_income": {"type": "number"},
                "willingness_to_travel": {"type": "number"},
                "special_requests": {"type": "number"}
            },
            "required": [
                "relationship_goals",
                "appearance",
                "location",
                "spirituality",
                "personality_attributes",
                "age",
                "interests",
                "identity_and_preference",
                "kids",
                "smoking",
                "pets",
                "career_goals",
                "annual_income",
                "willingness_to_travel",
                "special_requests"
            ],
            "additionalProperties": False
        }
    }

    # Call OpenAI API to get weights
    response = call_openai_assistant_batch(json_schema, all_messages_batch)
    if response and len(response) > 0:
        try:
            # Parse the JSON response to get weights
            weights = json.loads(response[0])
            print(f"Generated weights: {weights}")
            return weights
        except (json.JSONDecodeError, IndexError):
            print("Error decoding weights response.")
            return {}
    return {}

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

    # Fetch user profiles
    user = get_user_profile(user_id, tableProfile)
    all_users = get_all_user_profiles(tableProfile)

    if not user or not all_users:
        return {"error": "Failed to fetch user profiles"}

    # Generate dynamic weights based on the user profile using OpenAI API
    weights = generate_dynamic_weights(user)

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

        print("Compatibility scores:")
        for user_id, score in compatibility_scores.items():
            print(f"User ID: {user_id}, Compatibility Score: {score}")

        print(f"Top match: {top_match}")

    return {
        "user": user,
        "compatibility_scores": compatibility_scores,
        "top_match": top_match
    }

# Example usage
# tableProfile should be the DynamoDB or any other database resource being passed here
# user_id is the ID of the user for whom matchmaking needs to be run
# run_matchmaking_algorithm(user_id, tableProfile)
