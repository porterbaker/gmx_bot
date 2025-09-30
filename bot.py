# bot.py
from web3 import Web3
import requests
import os
import time

# --- GMX SDK Imports ---
from gmx_python_sdk.scripts.v2.gmx_utils import ConfigManager
from gmx_python_sdk.scripts.v2.gas_utils import *
from example_scripts.get_positions import get_positions
from gmx_python_sdk.scripts.v2.order.create_swap_order import SwapOrder
from gmx_python_sdk.scripts.v2.order.create_increase_order import IncreaseOrder
from gmx_python_sdk.scripts.v2.order.create_decrease_order import DecreaseOrder

# --- CONFIG ---
config = ConfigManager("arbitrum")
config.set_config()
wallet_address = Web3.to_checksum_address(config.user_wallet_address)

debug_mode = False  # Toggle debug/live
stable_token = "USDC"
poll_interval = 900  # 15 minutes
trade_fraction = 0.25
trade_size_fallback = 1000
slippage_percent = 0.5  # 0.5% default

# --- API & Web3 ---
rpc_url = "https://arbitrum.meowrpc.com"
arbi_market_info = "https://arbitrum-api.gmxinfra.io/markets/info"

w3 = Web3(Web3.HTTPProvider(rpc_url))
USDC_ADDRESS = Web3.to_checksum_address("0xaf88d065e77c8cC2239327C5EDb3A432268e5831")
erc20_abi = [
    {"constant": True, "inputs": [{"name": "_owner", "type": "address"}],
     "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"}
]

pairs_list = []

# --- BALANCE FUNCTIONS ---
def get_usdc_balance(address):
    try:
        usdc = w3.eth.contract(address=USDC_ADDRESS, abi=erc20_abi)
        balance_raw = usdc.functions.balanceOf(address).call()
        decimals = usdc.functions.decimals().call()
        balance = balance_raw / (10 ** decimals)
        if balance <= 0:
            print(f"[WARN] USDC balance zero for {address}, using fallback {trade_size_fallback}")
            return trade_size_fallback
        return balance
    except Exception as e:
        print(f"[WARN] Could not fetch USDC balance: {e}, using fallback {trade_size_fallback}")
        return trade_size_fallback

def get_trade_amount_fraction():
    return get_usdc_balance(wallet_address) * trade_fraction

# --- TOKEN PAIRS ---
def save_token_pairs_if_missing(data, filename="token_pairs.txt"):
    global pairs_list
    if not os.path.exists(filename):
        with open(filename, "w") as f:
            for market in data.get("markets", []):
                f.write(market.get("name", "") + "\n")
        print(f"Saved token pairs to {filename}")
    else:
        print(f"{filename} already exists, not overwriting.")
    
    with open(filename, "r") as f:
        for line in f:
            if "-USDC]" in line:
                pairs_list.append(line.strip())

# --- BEST SHORT PAIR ---
def best_short_pair(data, pair_names):
    markets = data.get("markets", [])
    liquidity_values = []
    for market in markets:
        try:
            liq_long = int(market.get("availableLiquidityLong", 0))
            liq_short = int(market.get("availableLiquidityShort", 0))
            liquidity_values.append(liq_long + liq_short)
        except:
            continue
    if not liquidity_values:
        return None, None

    threshold = sorted(liquidity_values)[len(liquidity_values)//2]

    candidate_markets = []
    for market in markets:
        name = market.get("name", "")
        if not any(p in name for p in pair_names):
            continue
        try:
            liq_long = int(market.get("availableLiquidityLong", 0))
            liq_short = int(market.get("availableLiquidityShort", 0))
            combined = liq_long + liq_short
            if combined >= threshold:
                candidate_markets.append((market, combined))
        except:
            continue

    best_market = None
    best_rate = 0
    for market, combined in candidate_markets:
        try:
            raw_short = float(market.get("netRateShort", 0))
        except:
            continue
        if raw_short < best_rate:
            best_rate = raw_short
            best_market = market

    if best_market:
        return best_market.get("name"), best_rate
    return None, None

# --- TOKEN ADDRESS MAP ---
def get_token_address_map():
    """Fetch GMX token list and return a dict mapping symbol -> address"""
    url = "https://arbitrum-api.gmxinfra.io/tokens"
    token_data = requests.get(url).json()
    token_map = {t["symbol"]: Web3.to_checksum_address(t["address"]) for t in token_data["tokens"]}
    return token_map

token_map = get_token_address_map()

# --- ORDER FUNCTIONS USING API DATA ---
def open_short(market_name, market_data, token_map):
    """Open a short position on the specified market using GMX API data."""
    amount_usdc = get_trade_amount_fraction()
    
    # Find the market info from API
    market_info = next(
        (m for m in market_data["markets"] if m["name"] == market_name),
        None
    )
    if not market_info:
        print(f"[WARN] Market {market_name} not found in API data")
        return

    market_key = Web3.to_checksum_address(market_info["marketToken"])
    index_token_address = Web3.to_checksum_address(market_info["indexToken"])
    collateral_address = Web3.to_checksum_address(market_info["shortToken"])
    swap_path = [collateral_address, index_token_address]
    is_long = False

    if debug_mode:
        print(f"[DEBUG] Opening short on {market_name}: {amount_usdc} {stable_token} -> {market_info['indexToken']}")
        return

    # SwapOrder: USDC -> Index Token
    swap_order = SwapOrder(
        config=config,
        start_token=swap_path[0],
        out_token=swap_path[1],
        size_delta=amount_usdc,
        market_key=market_key,
        collateral_address=collateral_address,
        index_token_address=index_token_address,
        is_long=is_long,
        initial_collateral_delta_amount=amount_usdc,
        slippage_percent=slippage_percent,
        swap_path=swap_path
    )
    swap_tx = swap_order.execute()
    print(f"Swap tx: {swap_tx}")

    # Increase Short Position
    increase_order = IncreaseOrder(
        config=config,
        market_key=market_key,
        collateral_address=collateral_address,
        index_token_address=index_token_address,
        is_long=is_long,
        size_delta=amount_usdc,
        initial_collateral_delta_amount=amount_usdc,
        slippage_percent=slippage_percent,
        swap_path=swap_path,
        execution_type=None
    )
    tx = increase_order.execute()
    print(f"Short tx: {tx}")


def close_short(market_name, market_data, token_map):
    """Close an existing short position."""
    # Find the market info from API
    market_info = next(
        (m for m in market_data["markets"] if m["name"] == market_name),
        None
    )
    if not market_info:
        print(f"[WARN] Market {market_name} not found in API data")
        return

    market_key = Web3.to_checksum_address(market_info["marketToken"])
    index_token_address = Web3.to_checksum_address(market_info["indexToken"])
    collateral_address = Web3.to_checksum_address(market_info["shortToken"])
    swap_path = [index_token_address, collateral_address]
    is_long = False

    if debug_mode:
        print(f"[DEBUG] Closing short on {market_name}")
        return

    # Decrease Short Position
    decrease_order = DecreaseOrder(
        config=config,
        market_key=market_key,
        collateral_address=collateral_address,
        index_token_address=index_token_address,
        is_long=is_long,
        size_delta="ALL",
        collateral_delta_amount="ALL",
        slippage_percent=slippage_percent,
        swap_path=swap_path,
        execution_type=None
    )
    tx = decrease_order.execute()
    print(f"Close tx: {tx}")

    # Swap back Index Token -> USDC
    swap_back = SwapOrder(
        config=config,
        start_token=swap_path[0],
        out_token=swap_path[1],
        size_delta="ALL",
        market_key=market_key,
        collateral_address=collateral_address,
        index_token_address=index_token_address,
        is_long=is_long,
        initial_collateral_delta_amount="ALL",
        slippage_percent=slippage_percent,
        swap_path=swap_path
    )
    swap_tx = swap_back.execute()
    print(f"Swap back tx: {swap_tx}")

# --- MAIN LOOP USING API DATA ---
if __name__ == "__main__":
    current_pair = None
    while True:
        try:
            # 1. Fetch latest market info
            market_info = requests.get(arbi_market_info).json()
            
            # 2. Save token pairs if missing
            save_token_pairs_if_missing(market_info)
            
            # 3. Determine best short pair
            best_pair, best_rate = best_short_pair(market_info, pairs_list)
            print(f"Best Current Short Funding: {best_pair}, rate={best_rate}")

            # 4. Fetch current positions
            positions = get_positions(config=config)

            if positions:
                # Extract token symbol from open position
                open_position_token = str(next(iter(positions))).split("_")[0]
                best_pair_token = best_pair.split("/")[0]

                if best_pair_token == open_position_token:
                    print("Best funding already established! Checking again in 15 minutes...")
                else:
                    print(f"Switching pairs: {open_position_token} -> {best_pair_token}")
                    close_short(current_pair, market_info, token_map)
                    open_short(best_pair, market_info, token_map)
                    current_pair = best_pair
            else:
                print("No open position, opening best short...")
                open_short(best_pair, market_info, token_map)
                current_pair = best_pair

        except Exception as e:
            print(f"[LOOP ERROR] {e}")

        time.sleep(poll_interval)
