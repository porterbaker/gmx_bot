from eth_abi import encode
from web3 import Web3
import requests
from gmx_python_sdk.scripts.v2.gmx_utils import *
from gmx_python_sdk.scripts.v2.gas_utils import *
from gmx_python_sdk.scripts.v2.order.create_increase_order import IncreaseOrder
from example_scripts.get_positions import get_positions, transform_open_position_to_order_parameters

config = ConfigManager("arbitrum")
config.set_config()
import os

rpc_url = "https://arbitrum.meowrpc.com"
arbi_tokens = "https://arbitrum-api.gmxinfra.io/tokens"
arbi_fees = "https://arbitrum-api.gmxinfra.io/apy?period=total"
arbi_market_info = "https://arbitrum-api.gmxinfra.io/markets/info"
arbi_prices = "https://arbitrum-api.gmxinfra.io/signed_prices/latest"
arbi_price_btc = "https://arbitrum-api.gmxinfra.io/prices/candles?tokenSymbol=BTC&period=1m"

web3_obj = Web3(Web3.HTTPProvider(rpc_url))

# Function to get net rates for a given pair (e.g., "BTC/USD")
def get_net_rates(data, pair_name):
    for market in data.get("markets", []):
        if pair_name in market.get("name", ""):
            net_rate_long = market.get("netRateLong")
            net_rate_short = market.get("netRateShort")
            if net_rate_short[0] == "-":
                nrs = net_rate_short[1:]
                nrl = "-" + net_rate_long[:-28] + "." + net_rate_long[-28:]
                nrs = nrs[:-28] + "." + nrs[-28:]
            if net_rate_long[0] == "-":
                nrl = net_rate_long[1:]
                nrs = "-" + net_rate_short[:-28] + "." + net_rate_short[-28:]
                nrl = nrl[:-28] + "." + nrl[-28:]
    return nrl, nrs

def save_token_pairs_if_missing(data, filename="token_pairs.txt"):
    if not os.path.exists(filename):  # only save if file doesn't exist
        with open(filename, "w") as f:
            for market in data.get("markets", []):
                f.write(market.get("name", "") + "\n")
        print(f"Saved token pairs to {filename}")
    else:
        print(f"{filename} already exists, not overwriting.")

def pull_token_pricing(data):
    candle_sticks = data.get("candles")
    latest_open = candle_sticks[0][1]
    latest_high = candle_sticks[0][2]
    latest_low = candle_sticks[0][3]
    latest_close = candle_sticks[0][4]
    print(f"\nLatest Prices within last 1m:\nOpen: ${latest_open}\nHigh: ${latest_high}\nLow: ${latest_low}\nClose: ${latest_close}\n")
    return latest_open, latest_high, latest_low, latest_close

try:
    response = requests.get(arbi_prices)
    #response2 = requests.get(arbi_fees)
    response2 = requests.get(arbi_market_info)
    response3 = requests.get(arbi_price_btc)

    if response2.status_code == 200:
        print("Connection success!")
        response3_json = response3.json()
        response2_json = response2.json()
        response_json = response.json()

        save_token_pairs_if_missing(response2_json)

        nrl_btcusd, nrs_btcusd = get_net_rates(response2_json, "BTC/USD [WBTC.b-USDC]")
        nrl_btcusd, nrs_btcusd = float(nrl_btcusd), float(nrs_btcusd)
        print(f"Long: {nrl_btcusd}%")
        print(f"Short: {nrs_btcusd}%")
        btc_open, btc_high, btc_low, btc_close = pull_token_pricing(response3_json)

        positions = get_positions(
            config=config
        )

        order_param = transform_open_position_to_order_parameters(config, positions, "BTC", False, 0.003, "USDC", 1, 1)
        print(order_param)

except requests.RequestException as e:
        print(f"Error: {e}")


