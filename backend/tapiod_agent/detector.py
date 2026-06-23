import ast
import json
import math
import traceback
from datetime import datetime

import requests


# ── Tool implementations ───────────────────────────────────────────────────────

def get_current_weather(arguments: dict) -> str:
    """Current weather via Open-Meteo (no API key required)."""
    try:
        location = arguments.get("location", "").strip()
        if not location:
            return json.dumps({"error": "No location provided."})
        geo = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": location.split(",")[0].strip(), "count": 1, "language": "en", "format": "json"},
            timeout=5,
        ).json()
        if not geo.get("results"):
            return json.dumps({"error": f"Could not find coordinates for: {location}"})
        r = geo["results"][0]
        lat, lon, name = r["latitude"], r["longitude"], r["name"]
        weather = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
                "temperature_unit": "fahrenheit",
            },
            timeout=5,
        ).json()
        wmo = {
            0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
            45: "Fog", 51: "Light drizzle", 61: "Slight rain", 63: "Moderate rain",
            65: "Heavy rain", 71: "Slight snow", 73: "Moderate snow", 95: "Thunderstorm",
        }
        c = weather.get("current", {})
        return json.dumps({
            "location": name,
            "temperature_f": c.get("temperature_2m"),
            "condition": wmo.get(c.get("weather_code", 0), "Unknown"),
            "humidity_pct": c.get("relative_humidity_2m"),
            "wind_mph": c.get("wind_speed_10m"),
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


def calculate_expression(arguments: dict) -> str:
    """Safe math expression evaluator."""
    expression = arguments.get("expression", "").strip()
    if not expression:
        return json.dumps({"error": "No expression provided."})
    safe_names = {
        "sqrt": math.sqrt, "abs": abs, "round": round,
        "sin": math.sin, "cos": math.cos, "tan": math.tan,
        "log": math.log, "log2": math.log2, "log10": math.log10,
        "exp": math.exp, "ceil": math.ceil, "floor": math.floor,
        "pi": math.pi, "e": math.e, "inf": math.inf,
    }
    allowed = (
        ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant,
        ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod, ast.FloorDiv,
        ast.USub, ast.UAdd, ast.Call, ast.Name, ast.Load,
    )
    try:
        tree = ast.parse(expression, mode="eval")
        for node in ast.walk(tree):
            if not isinstance(node, allowed):
                return json.dumps({"error": f"Disallowed operation: {type(node).__name__}"})
            if isinstance(node, ast.Name) and node.id not in safe_names:
                return json.dumps({"error": f"Unknown name: {node.id}"})
        result = eval(compile(tree, "<expr>", "eval"), {"__builtins__": {}}, safe_names)  # noqa: S307
        return json.dumps({"expression": expression, "result": result})
    except ZeroDivisionError:
        return json.dumps({"error": "Division by zero."})
    except Exception as e:
        return json.dumps({"error": f"Could not evaluate: {e}"})


def get_stock_price(arguments: dict) -> str:
    """Latest market price via Yahoo Finance (no API key required)."""
    symbol = arguments.get("symbol", "").strip().upper()
    if not symbol:
        return json.dumps({"error": "No ticker symbol provided."})
    try:
        resp = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
            params={"interval": "1d", "range": "1d"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=6,
        )
        data = resp.json()
        result = data.get("chart", {}).get("result")
        if not result:
            err = data.get("chart", {}).get("error", {})
            return json.dumps({"error": err.get("description", f"Symbol '{symbol}' not found.")})
        meta = result[0]["meta"]
        price = meta.get("regularMarketPrice") or meta.get("chartPreviousClose")
        prev = meta.get("chartPreviousClose") or price
        change = round(price - prev, 4) if price and prev else None
        change_pct = round((change / prev) * 100, 2) if change is not None and prev else None
        return json.dumps({
            "symbol": symbol,
            "price": price,
            "currency": meta.get("currency", "USD"),
            "exchange": meta.get("exchangeName", ""),
            "change": change,
            "change_pct": change_pct,
            "market_state": meta.get("marketState", ""),
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


_CITY_TZ = {
    "new york": "America/New_York", "los angeles": "America/Los_Angeles",
    "chicago": "America/Chicago", "london": "Europe/London",
    "paris": "Europe/Paris", "berlin": "Europe/Berlin",
    "dubai": "Asia/Dubai", "mumbai": "Asia/Kolkata",
    "delhi": "Asia/Kolkata", "beijing": "Asia/Shanghai",
    "tokyo": "Asia/Tokyo", "singapore": "Asia/Singapore",
    "sydney": "Australia/Sydney", "toronto": "America/Toronto",
}


def get_time_in_timezone(arguments: dict) -> str:
    """Current time in any city or IANA timezone."""
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    location = arguments.get("location", "").strip()
    if not location:
        return json.dumps({"error": "No location provided."})
    tz_name = _CITY_TZ.get(location.lower(), location)
    try:
        tz = ZoneInfo(tz_name)
        now = datetime.now(tz)
        return json.dumps({
            "location": location,
            "timezone": tz_name,
            "current_time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "day_of_week": now.strftime("%A"),
            "utc_offset": now.strftime("%z"),
        })
    except ZoneInfoNotFoundError:
        return json.dumps({"error": f"Unknown timezone or city: '{location}'."})
    except Exception as e:
        return json.dumps({"error": str(e)})


def web_search(arguments: dict) -> str:
    """Web search via DuckDuckGo Instant Answer API."""
    query = arguments.get("query", "").strip()
    if not query:
        return json.dumps({"error": "No search query provided."})
    try:
        resp = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=6,
        )
        data = resp.json()
        results = []
        if data.get("AbstractText"):
            results.append({"source": data.get("AbstractSource", ""), "text": data["AbstractText"], "url": data.get("AbstractURL", "")})
        for item in data.get("RelatedTopics", [])[:4]:
            if isinstance(item, dict) and item.get("Text"):
                results.append({"text": item["Text"], "url": item.get("FirstURL", "")})
        return json.dumps({"query": query, "results": results})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ── Registry + dispatcher ──────────────────────────────────────────────────────

TOOL_REGISTRY: dict = {
    "get_current_weather":  get_current_weather,
    "calculate_expression": calculate_expression,
    "get_stock_price":      get_stock_price,
    "get_time_in_timezone": get_time_in_timezone,
    "web_search":           web_search,
}

MOCK_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_current_weather",
            "description": "Get the current weather conditions for a city or location.",
            "parameters": {"type": "object", "properties": {"location": {"type": "string"}}, "required": ["location"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_expression",
            "description": "Calculate or evaluate any math expression and return the exact numeric result.",
            "parameters": {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_price",
            "description": "Get the latest market price for a stock ticker symbol.",
            "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_time_in_timezone",
            "description": "Get the current time in any city or IANA timezone.",
            "parameters": {"type": "object", "properties": {"location": {"type": "string"}}, "required": ["location"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for information using DuckDuckGo.",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        },
    },
]


def execute_tool(tool_call: dict) -> str:
    """Dispatch an OpenAI-format tool_call to the matching Python function."""
    try:
        func_data = tool_call.get("function", {})
        name = func_data.get("name")
        args_str = func_data.get("arguments", "{}")
        if not name or name not in TOOL_REGISTRY:
            return json.dumps({"error": f"Tool '{name}' not found in registry."})
        try:
            arguments = json.loads(args_str)
        except json.JSONDecodeError:
            return json.dumps({"error": "Could not parse tool arguments as JSON."})
        print(f"[Detector] {name}({arguments})")
        result = TOOL_REGISTRY[name](arguments)
        print(f"[Detector] → {result[:120]}")
        return result
    except Exception as e:
        return json.dumps({"error": f"Tool execution failed: {e}", "trace": traceback.format_exc()})
