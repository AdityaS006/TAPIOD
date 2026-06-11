import requests
import json
import traceback

def get_current_weather(arguments: dict) -> str:
    """
    Fetches current weather for a given location using Open-Meteo.
    """
    try:
        location = arguments.get("location", "")
        if not location:
            return json.dumps({"error": "No location provided"})
            
        # 1. Geocode the location (Open-Meteo prefers just the city name without country codes)
        clean_location = location.split(",")[0].strip()
        geocode_url = "https://geocoding-api.open-meteo.com/v1/search"
        geo_res = requests.get(geocode_url, params={
            "name": clean_location,
            "count": 1,
            "language": "en",
            "format": "json"
        })
        geo_data = geo_res.json()
        
        if not geo_data.get("results"):
            return json.dumps({"error": f"Could not find coordinates for location: {location}"})
            
        result = geo_data["results"][0]
        lat = result["latitude"]
        lon = result["longitude"]
        name = result["name"]
        
        # 2. Fetch the weather
        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m&temperature_unit=fahrenheit"
        weather_res = requests.get(weather_url)
        weather_data = weather_res.json()
        
        current = weather_data.get("current", {})
        
        # Open-Meteo WMO Weather codes
        wmo_codes = {
            0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
            45: "Fog", 48: "Depositing rime fog", 51: "Light drizzle", 53: "Moderate drizzle",
            55: "Dense drizzle", 61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
            71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow", 95: "Thunderstorm"
        }
        
        condition = wmo_codes.get(current.get("weather_code", 0), "Unknown")
        
        output = {
            "location": name,
            "temperature_fahrenheit": current.get("temperature_2m"),
            "condition": condition,
            "humidity_percent": current.get("relative_humidity_2m"),
            "wind_speed_mph": current.get("wind_speed_10m"),
        }
        
        return json.dumps(output)
        
    except Exception as e:
        return json.dumps({"error": f"Tool execution failed: {str(e)}", "traceback": traceback.format_exc()})

# Registry mapping tool names to functions
TOOL_REGISTRY = {
    "get_current_weather": get_current_weather
}

def execute_tool(tool_call: dict) -> str:
    """
    Executes a tool call based on its name and arguments.
    tool_call format (OpenAI format):
    {
      "id": "call_123",
      "type": "function",
      "function": {
        "name": "get_current_weather",
        "arguments": "{\"location\": \"Tokyo\"}"
      }
    }
    """
    try:
        func_data = tool_call.get("function", {})
        name = func_data.get("name")
        arguments_str = func_data.get("arguments", "{}")
        
        if not name or name not in TOOL_REGISTRY:
            return json.dumps({"error": f"Tool '{name}' not found in registry."})
            
        try:
            arguments = json.loads(arguments_str)
        except json.JSONDecodeError:
            return json.dumps({"error": "Failed to parse tool arguments as JSON."})
            
        print(f"[ToolExecutor] Executing {name} with args: {arguments}")
        result = TOOL_REGISTRY[name](arguments)
        print(f"[ToolExecutor] Result: {result}")
        return result
        
    except Exception as e:
        return json.dumps({"error": f"Tool execution pipeline failed: {str(e)}"})
