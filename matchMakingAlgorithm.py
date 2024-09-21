import json
from itertools import combinations
import openai
import os
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

openai.api_key = OPENAI_API_KEY


def call_openai_assistant(json_schema, all_messages):
        # Make the API call with the new interface
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=all_messages,
            response_format={
                "type": "json_schema",
                "json_schema": json_schema
            }
        )

        assistant_response = response.choices[0].message.content

        # Return the response
        return assistant_response

def get_user_profile(user_id: str, tableProfile) -> Optional[dict]:
    try:
        response = tableProfile.get_item(
            Key={
                'UserID': user_id
            }
        )
        return response
    except Exception as e:
        print(f"Error fetching user profile: {e}")
        return None

def get_all_user_profiles(tableProfile) -> Optional[List[dict]]:
    try:
        response = tableProfile.scan()
        return response["Items"]
    except Exception as e:
        print(f"Error fetching all user profiles: {e}")
        return None

def run_matchmaking_algorithm(user_id: str, tableProfile: any):
    # Initialize OpenAI API with the provided API key

    # Matchmaking Algorithm
    json_schema = {
        "name": "matchmaking_score",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "compatibility_score": {
                    "type": "integer"
                }
            },
            "required": [
                "compatibility_score"
            ],
            "additionalProperties": False
        }
    }
    all_messages = [{
        "role": "system",
        "content": '''You're an expert matchmaker. You'll be given attributes from 2 different people's matchmaking profiles in JSON format, compare them and output a compatibility score (on a scale of 1 to 10). Think carefully.'''
    }]

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

    user = get_user_profile(user_id, tableProfile)
    all_users = get_all_user_profiles(tableProfile)
    # # Sample data
    # sample_data = {
    #     "user_id_3628": matchmakingAlgoResources.sample_user_profile_1,
    #     "user_id_1820": matchmakingAlgoResources.sample_user_profile_2,
    # }

    # # Get all possible pairs of user IDs
    # user_pairs = list(combinations(sample_data.keys(), 2))
    # compatibility_score_for_all_users = {}

    # for user_pair in user_pairs:
    #     # Extract the actual user profiles using the keys
    #     user_profile_1 = sample_data[user_pair[0]]["user_profile"]
    #     user_profile_2 = sample_data[user_pair[1]]["user_profile"]

    #     compatibility_score = 0
    #     # For each possible pair of users, compare their attributes
    #     for attribute in user_profile_1:
    #         # Serialize the content dictionary to a JSON string
    #         content_dict = {
    #             "Person 1": user_profile_1[attribute],
    #             "Person 2": user_profile_2[attribute]
    #         }

    #         all_messages.append({
    #             "role": "user",
    #             "content": json.dumps(content_dict)  # Convert content to a JSON string
    #         })

    #         # Make the assistant API call
    #         assistant_response = call_openai_assistant(json_schema, all_messages)
    #         attribute_score = json.loads(assistant_response)["compatibility_score"]
    #         print(attribute + " score is = " + str(attribute_score))
        
    #         compatibility_score += attribute_score * weights[attribute]

    #     compatibility_score_for_all_users[user_pair] = compatibility_score

    return {user, all_users}
