import json

def generate_mock_tools():
    # Properly defined weather tool
    weather_tool = {
        "type": "function",
        "function": {
            "name": "get_current_weather",
            "description": "Get the current weather conditions for a specific city or location.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city and state/country, e.g., 'San Francisco, CA' or 'Tokyo, Japan'."
                    }
                },
                "required": ["location"]
            }
        }
    }
    
    # We only have one fully implemented tool on the backend!
    # Removing all the fake placeholders so the demo doesn't hallucinate.
    tools = [weather_tool]
            
    return tools

MOCK_TOOLS = generate_mock_tools()
