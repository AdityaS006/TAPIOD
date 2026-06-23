import json
import sys

try:
    with open('previous_transcript.jsonl', 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f if line.strip()]
        
    for line in lines[-20:]: # Get last 20 lines
        try:
            obj = json.loads(line)
            if obj.get('type') in ('USER_INPUT', 'PLANNER_RESPONSE', 'TOOL_RESPONSE'):
                if obj.get('type') == 'USER_INPUT':
                    print("USER:", obj.get('content', ''))
                elif obj.get('type') == 'PLANNER_RESPONSE':
                    print("MODEL:", obj.get('content', ''), obj.get('tool_calls', ''))
                elif obj.get('type') == 'TOOL_RESPONSE':
                    # only print brief if it's too long
                    content = str(obj.get('content', ''))
                    print("TOOL:", content[:100])
                print("-" * 40)
        except json.JSONDecodeError:
            pass
except Exception as e:
    print("Error:", e)
