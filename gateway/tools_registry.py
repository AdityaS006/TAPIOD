MOCK_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_weather",
            "description": (
                "Get the current weather conditions for a city or location. "
                "Use this for questions like 'what is the weather in X', "
                "'is it raining in Y', 'temperature in Z', 'how hot is it in'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City name, e.g. 'Tokyo' or 'New York, NY'.",
                    }
                },
                "required": ["location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_expression",
            "description": (
                "Calculate or evaluate any math expression and return the exact numeric result. "
                "Use this when a user asks 'what is X', 'calculate X', 'compute X', 'solve X', "
                "'how much is X', or any arithmetic, algebra, percentage, square root, "
                "power, trigonometry, or equation. "
                "Supports: +, -, *, /, **, sqrt, sin, cos, tan, log, abs, round, pi, e."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "A math expression, e.g. '17 * 43 + sqrt(144)' or 'sin(pi/4)'.",
                    }
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_price",
            "description": (
                "Get the current or latest market price for a stock or ETF by its ticker symbol. "
                "Use this for questions like 'what is the price of AAPL', 'TSLA stock today', "
                "'how is NVDA doing', 'current value of S&P 500 ETF'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Stock ticker symbol, e.g. 'AAPL', 'TSLA', 'MSFT', 'SPY'.",
                    }
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_time_in_timezone",
            "description": (
                "Get the current date and time in any city or timezone around the world. "
                "Use this for questions like 'what time is it in Tokyo', 'current time in London', "
                "'what time is it in New York right now', 'time difference with Paris'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City name or IANA timezone string, e.g. 'Tokyo', 'London', 'America/New_York'.",
                    }
                },
                "required": ["location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web for current information, news, facts, or any topic. "
                "Use this when the user asks about recent events, news, latest developments, "
                "current prices, trending topics, or anything that requires up-to-date information "
                "beyond the model's training data."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query, e.g. 'latest AI news 2025' or 'Python 3.13 release notes'.",
                    }
                },
                "required": ["query"],
            },
        },
    },
]
