import requests
import time

arbi_market_info = "https://arbitrum-api.gmxinfra.io/markets/info"

connection = True
while connection:
    try:
        response = requests.get(arbi_market_info)
        if response.status_code == 200:
            print("Connection Success!")
    except requests.RequestException as e:
        connection = False
        print(f"Error: {e}")
    
    time.sleep(30)