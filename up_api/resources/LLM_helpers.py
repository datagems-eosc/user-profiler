import json, requests, os

TOKEN = os.getenv('LLM_TOKEN', '')
LLM_API_URL = os.getenv('LLM_API_URL', '')
HEADERS = {
"User-Agent": "Python API Sample",
"Authorization": "Bearer " + TOKEN,
"Content-Type": "application/json"
}


def get_user_previous_queries(profile: dict) -> str:
    """
    Extracts all query texts from every session in a user profile dict
    and joins them with the ' | ' separator expected by the LLM prompt.
    """
    texts = [
        q["text"]
        for session in profile.get("sessions", [])
        if not session.get("extracted")
        for q in session.get("queries", [])
        if q.get("text")
    ]
    return " | ".join(texts)


def generate_keywords_from_session(context: dict, model_choice: str = "llama-3.3") -> str:
    queries_from_session = get_user_previous_queries(context)
    payload = {
            "model": model_choice,
            "messages": [
                {
                    "role":"system",
                    "content": '''You are an AI assistant whose primary goal is to extract keywords from a user chat session.
                    A chat session is defined by a set of queries that the user performed in a data analytics app.
                    Two different queries and entities are separated by the token '|'. For example,'Microsoft' and 'Google' would appear as 'Microsoft' | 'Google'.
                    Provide a list of keywords that are relevant to this session.
                    Only suggest a list of keywords, in the format: ['key1', 'key2', 'key3', ...].
                    Do not write any additional text, only the list of keywords. 
                    '''
    
                },
                {
                    "role":"user",
                    "content":f'''User's previous queries: {queries_from_session}'''
                }
            ]
        }

    json_data = json.dumps(payload).encode('utf8')
    
    try:
        response = requests.post(url=LLM_API_URL, headers=HEADERS, data=json_data, verify=False, timeout=120)
        response.raise_for_status()
        res = response.json()['choices'][0]['message']['content']
        return res
    except requests.exceptions.RequestException as e:
        print("Error while calling API:", e)
        return None