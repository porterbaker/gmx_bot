# paper_bot.py
import requests
import os
import time
from web3 import Web3
import random

# --- CONFIG ---
rpc_url = "https://arbitrum.meowrpc.com"
wallet_address = "0xPAPER_WALLET"  # dummy address for simulation
poll_interval = 900  # 15 minutes
trade_fraction = 0.25  # 1/4th per swap + short
debug_mode = True

# Simulation wallet
wallet = {
    "USDC": 10000.0,  # starting USDC balance
    "positions": {},  # {token: {"size": USDC_value, "side": "short"}}
    "funding_earned": 0.0,
    "gas_spent": 0.0,
}

# --- API ---
arbi_market_info = "https://arbitrum-api.gmxinfra.io/markets/info"

pairs_list = []

def save_token_pairs_if_missing(data, filename="token_pairs.txt"):
    global pairs_list
    if not os.path.exists(filename):
        with open(filename, "w") as f:
            for market in data.get("markets", []):
                f.write(market.get("name", "") + "\n")
        print(f"Saved token pairs to {filename}")
    else:
        print(f"{filename} already exists, not overwriting.")
    with open("token_pairs.txt", "r") as f:
        for line in f:
            if "-USDC]" in line:
                pairs_list.append(line.strip())

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
    liquidity_values.sort()
    threshold = liquidity_values[len(liquidity_values) // 2]

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

# --- PAPER TRADING FUNCTIONS ---
def get_trade_amount_fraction():
    return wallet["USDC"] * trade_fraction

def simulate_gas_cost():
    # estimate gas cost for swap + short (in USDC)
    gas_usdc = random.uniform(0.5, 2.0)  # simulate $0.5-$2 per combo
    wallet["gas_spent"] += gas_usdc
    return gas_usdc

def open_short(market_name, rate):
    token = market_name.split("/")[0]
    amount_usdc = get_trade_amount_fraction()
    gas_cost = simulate_gas_cost()
    wallet["USDC"] -= amount_usdc + gas_cost
    wallet["positions"][token] = {"size": amount_usdc, "side": "short", "rate": rate}
    print(f"[PAPER] Opened short: {token} ${amount_usdc:.2f}, gas=${gas_cost:.2f}, rate={rate}")

def close_short(market_name):
    token = market_name.split("/")[0]
    if token not in wallet["positions"]:
        return
    pos = wallet["positions"].pop(token)
    # simulate funding fees earned
    funding_fee = pos["size"] * (-pos["rate"]) * random.uniform(0.8, 1.2)
    wallet["funding_earned"] += funding_fee
    # return USDC
    wallet["USDC"] += pos["size"]
    gas_cost = simulate_gas_cost()
    wallet["USDC"] -= gas_cost
    print(f"[PAPER] Closed short: {token}, funding earned=${funding_fee:.2f}, gas=${gas_cost:.2f}")

# --- MAIN LOOP ---
if __name__ == "__main__":
    current_pair = None
    while True:
        try:
            market_info = requests.get(arbi_market_info).json()
            save_token_pairs_if_missing(market_info)
            best_pair, best_rate = best_short_pair(market_info, pairs_list)
            if best_pair is None:
                print("[WARN] No valid pair found")
                time.sleep(poll_interval)
                continue
            print(f"[PAPER] Best pair: {best_pair}, rate={best_rate}")

            if current_pair:
                current_token = current_pair.split("/")[0]
                new_token = best_pair.split("/")[0]
                if new_token != current_token:
                    print("[PAPER] Switching pairs...")
                    close_short(current_pair)
                    open_short(best_pair, best_rate)
                    current_pair = best_pair
                else:
                    print("[PAPER] Maintaining current position...")
            else:
                print("[PAPER] Opening initial position...")
                open_short(best_pair, best_rate)
                current_pair = best_pair

            print(f"[PAPER] Wallet USDC: {wallet['USDC']:.2f}, Funding earned: {wallet['funding_earned']:.2f}, Gas spent: {wallet['gas_spent']:.2f}")

        except Exception as e:
            print(f"[PAPER LOOP ERROR] {e}")

        time.sleep(poll_interval)
