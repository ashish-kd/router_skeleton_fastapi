import os, json, time, random, string
import requests

API_URL = os.getenv("API_URL", "http://localhost:8000/route")
API_KEY = os.getenv("API_KEY", "dev-key")

def rand_text(n=16):
    import random, string
    return ''.join(random.choice(string.ascii_letters) for _ in range(n))

def one_request(i):
    payload = {"message": rand_text(32)}
    req = {"sender_id": f"user_{i%10}", "payload": payload}
    r = requests.post(API_URL, headers={"X-API-Key": API_KEY}, json=req, timeout=5)
    if r.status_code != 200:
        print("ERR", r.status_code, r.text)

def main():
    start = time.time()
    N = int(os.getenv("N", "1000"))
    for i in range(N):
        one_request(i)
    dur = time.time()-start
    print(f"Sent {N} in {dur:.2f}s")

if __name__ == "__main__":
    main()
