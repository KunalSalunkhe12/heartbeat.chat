import boto3
from boto3.dynamodb.conditions import Key

AWS_REGION = "us-east-1"  # Replace with your preferred AWS region
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
tableChat = dynamodb.Table('ChatMessages')
tableProfile = dynamodb.Table('UserProfiles')

# Assuming you've already set up your DynamoDB resource
dynamodb = boto3.resource('dynamodb')
tableChat = dynamodb.Table('YourChatTableName')  # Replace with your actual table name

def get_all_messages():
    """
    Fetch all messages from the DynamoDB Chat table.

    Returns:
    - A list of all messages or an empty list if none are found.
    """
    try:
        # Using scan to fetch all items from the table
        response = tableChat.scan()
        
        messages = response.get('Items', [])
        
        # Continue scanning until all messages are retrieved
        while 'LastEvaluatedKey' in response:
            response = tableChat.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            messages.extend(response.get('Items', []))

        print(f"Fetched messages: {messages}")
        return messages
    
    except Exception as e:
        print(f"Error fetching messages from DynamoDB: {e}")
        return []