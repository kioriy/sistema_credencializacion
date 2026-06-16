import requests

url = "https://app.miescuela.net/api/credentials/export"
headers = {
    "X-Credential-Key": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
    "Accept": "application/json"
}
try:
    response = requests.get(url, headers=headers)
    print(f"Status: {response.status_code}")
    print(response.text[:500])
except Exception as e:
    print(f"Error: {e}")
