import json, requests, os
from urllib.parse import urlsplit
import urllib3
from pydantic import ValidationError

from .data_models import LLMSessionKeywords

# Asks OpenAI-compatible backends to constrain the reply to this schema
KEYWORDS_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "session_keywords",
        "strict": True,
        "schema": LLMSessionKeywords.model_json_schema() | {"additionalProperties": False},
    },
}


# ==========================
# LLM API CONFIGURATION
# LLM Tokne 
TOKEN = os.getenv('LLM_TOKEN', '')

# LLM API URL
LLM_API_URL = os.getenv('LLM_API_URL', '')

# LLM Model List URL
LLM_MODEL_LIST = os.getenv('LLM_MODEL_LIST', '')

HEADERS = {
"User-Agent": "Python API Sample",
"Authorization": "Bearer " + TOKEN,
"Content-Type": "application/json"
}
#==========================



def _ssl_verify_setting() -> bool | str:
    """
    Reads LLM_SSL_VERIFY: "true" (default) verifies against the system CAs,
    a file path verifies against that CA bundle / certificate, and "false"
    disables verification (e.g. for an endpoint with a self-signed certificate).
    """
    value = os.getenv('LLM_SSL_VERIFY', 'true').strip()
    if value.lower() in ('false', '0', 'no'):
        # Explicit opt-out: warn once here instead of on every request
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        print("WARNING: TLS certificate verification for the LLM API is disabled (LLM_SSL_VERIFY=false)")
        return False
    if value.lower() in ('true', '1', 'yes', ''):
        return True
    return value

SSL_VERIFY = _ssl_verify_setting()


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


# hard coded the one of the installed LLM
def generate_keywords_from_session(context: dict, model_choice: str = "kimi-k2.6",
                                   queries: dict[str, str] | None = None) -> list[str] | None:
    """
    Returns the keywords extracted from the not-yet-extracted sessions, [] if there
    are no such queries, or None if the LLM could not be reached or replied with
    invalid output.
    """
    
    # using the user queries
    if queries is not None:
        queries_from_session = " | ".join(queries.values())
    else:
        queries_from_session = get_user_previous_queries(context)
    
    if not queries_from_session:
        return []

    model_available = get_available_models(model_choice)

    payload = {
            "model": model_available,
            "messages": [
                {
                    "role":"system",
                    "content": '''You are an AI assistant whose primary goal is to extract keywords from a user chat session.
                    A chat session is defined by a set of queries that the user performed in a data analytics app.
                    Two different queries and entities are separated by the token '|'. For example,'Microsoft' and 'Google' would appear as 'Microsoft' | 'Google'.
                    Provide a list of keywords that are relevant to this session.
                    Reply ONLY with a JSON object of this exact form, with no other text:
                    {"keywords": ["key1", "key2", "key3"]}
                    '''

                },
                {
                    "role":"user",
                    "content":f'''User's previous queries: {queries_from_session}'''
                }
            ],
            "response_format": KEYWORDS_RESPONSE_FORMAT,
        }

    try:
        response = requests.post(url=LLM_API_URL, headers=HEADERS, data=json.dumps(payload).encode('utf8'), verify=SSL_VERIFY, timeout=120)
        if response.status_code == 400:
            # Some backends/models reject response_format: retry relying on the prompt alone
            del payload["response_format"]
            response = requests.post(url=LLM_API_URL, headers=HEADERS, data=json.dumps(payload).encode('utf8'), verify=SSL_VERIFY, timeout=120)
        response.raise_for_status()
        content = response.json()['choices'][0]['message']['content']
    except requests.exceptions.RequestException as e:
        print("Error while calling API:", e)
        return None

    return parse_keywords(content)


def parse_keywords(content: str) -> list[str] | None:
    """
    Validates the LLM reply against LLMSessionKeywords and cleans the keywords:
    strips whitespace, drops empty ones and duplicates (case-insensitive).
    Returns None if the reply is not valid JSON of the expected shape.
    """
    # Tolerate replies wrapped in ```json fences or surrounded by extra text
    start, end = content.find('{'), content.rfind('}')
    if start == -1 or end == -1:
        print("LLM reply contains no JSON object:", content)
        return None

    try:
        parsed = LLMSessionKeywords.model_validate_json(content[start:end + 1])
    except ValidationError as e:
        print("LLM reply does not match the expected schema:", e)
        return None

    seen = set()
    keywords = []
    for k in parsed.keywords:
        k = k.strip()
        if k and k.lower() not in seen:
            seen.add(k.lower())
            keywords.append(k)
    return keywords



# function to automatically retrive the list of available LLMs' ID
def get_available_models(model_choice) -> str:
    '''
    This function will retrive via http request the available models to use inside
    the keywords generation function

    input:
        - model_choice model selected by user or defualt model

    Return:
        - ID of the available model: either the first available or the one selected
    '''

    # models endpoint lives at <scheme>://<host[:port]>/api/models, whatever the chat path is
    url = os.getenv('LLM_MODEL_LIST', '')

    try:
        response = requests.get(
        url,
        headers= HEADERS,
        verify=SSL_VERIFY,
        timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        models = [model["id"] for model in data["data"]]
        model_available = model_choice if model_choice in models else (models[0] if models else model_choice)
        return model_available
    
        
    except requests.exceptions.RequestException as e:
        print(f"Could not reach models endpoint: {e}")
        return model_choice