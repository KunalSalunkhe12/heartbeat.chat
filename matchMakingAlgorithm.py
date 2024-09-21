import json  # Needed for JSON serialization
from itertools import combinations

import matchmakingAlgoResources
import openAIAPICall

#Matchmaking Algorithm
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
    "content": '''You're an expert matchmaker. You'll be given attributes from 2 different people’s matchmaking profiles in JSON format, compare them and output a compatibility score (on a scale of 1 to 10). Think carefully.'''
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



# Sample data
sample_data = {
    "user_id_3628": matchmakingAlgoResources.sample_user_profile_1,
    "user_id_1820": matchmakingAlgoResources.sample_user_profile_2,
}

# Get all possible pairs of user IDs
user_pairs = list(combinations(sample_data.keys(), 2))
compatibility_score_for_all_users = {}

for user_pair in user_pairs:
    # Extract the actual user profiles using the keys
    user_profile_1 = sample_data[user_pair[0]]["user_profile"]
    user_profile_2 = sample_data[user_pair[1]]["user_profile"]

    compatibility_score = 0
    # For each possible pair of users, compare their attributes
    for attribute in user_profile_1:
        # Serialize the content dictionary to a JSON string
        content_dict = {
            "Person 1": user_profile_1[attribute],
            "Person 2": user_profile_2[attribute]
        }

        all_messages.append({
            "role": "user",
            "content": json.dumps(content_dict)  # Convert content to a JSON string
        })

        # Make the assistant API call
        assistant_response = openAIAPICall.call_openai_assistant(json_schema, all_messages)
        #print(type(assistant_response))
        attribute_score = json.loads(assistant_response)["compatibility_score"]
        print(attribute + " score is = " + str(attribute_score))
    
        compatibility_score += attribute_score * weights[attribute]

    compatibility_score_for_all_users[user_pair] = compatibility_score
