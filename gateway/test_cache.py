import requests
import json
import time

url = 'http://localhost:4000/v1/chat/completions'

headers = {
    'Authorization': 'Bearer sk-test-tenant1-12345',
    'Content-Type': 'application/json'
}

data = {
    'model': 'fast-model',
    'messages': [{'role': 'user', 'content': 'What is the capital of France? Tell me briefly.'}]
}

print('First request (should be a cache miss & write to cache):')
start = time.time()
try:
    res1 = requests.post(url, headers=headers, json=data)
    print(f'Time: {time.time()-start:.2f}s, Status: {res1.status_code}')
    if res1.status_code == 200:
        print(res1.json().get('choices', [{}])[0].get('message', {}).get('content', res1.text))
    else:
        print(res1.text)
except Exception as e:
    print(f'Failed: {e}')

print('\nSecond request (exact same prompt - should be an exact or semantic cache hit!):')
start = time.time()
res2 = requests.post(url, headers=headers, json=data)
print(f'Time: {time.time()-start:.2f}s, Status: {res2.status_code}')
if res2.status_code == 200:
    print(res2.json().get('choices', [{}])[0].get('message', {}).get('content', res2.text))

print('\nThird request (slightly different prompt - should be semantic hit!):')
data['messages'][0]['content'] = 'Can you briefly tell me the capital of France?'
start = time.time()
res3 = requests.post(url, headers=headers, json=data)
print(f'Time: {time.time()-start:.2f}s, Status: {res3.status_code}')
if res3.status_code == 200:
    print(res3.json().get('choices', [{}])[0].get('message', {}).get('content', res3.text))

print('\nFourth request (same meaning, DIFFERENT API KEY/TENANT - should be a MISS due to isolation!):')
headers2 = {
    'Authorization': 'Bearer sk-test-tenant2-abcde',
    'Content-Type': 'application/json'
}
start = time.time()
res4 = requests.post(url, headers=headers2, json=data)
print(f'Time: {time.time()-start:.2f}s, Status: {res4.status_code}')
if res4.status_code == 200:
    print(res4.json().get('choices', [{}])[0].get('message', {}).get('content', res4.text))
