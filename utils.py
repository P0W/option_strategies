## Author : Prashant Srivastava
## Last Modified Date  : Dec 26th, 2022

import requests
import logging
import json
from py5paisa import *


def get_india_vix() -> float:
    baseurl = "https://www.nseindia.com/"
    url = "https://www.nseindia.com/api/allIndices"
    headers = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, "
        "like Gecko) "
        "Chrome/80.0.3987.149 Safari/537.36",
        "accept-language": "en,gu;q=0.9,hi;q=0.8",
        "accept-encoding": "gzip, deflate, br",
    }
    try:
        session = requests.Session()
        request = session.get(baseurl, headers=headers, timeout=5)
        cookies = dict(request.cookies)
        response = session.get(url, headers=headers, timeout=5, cookies=cookies)
        if response.status_code == 200:
            indices_data = response.json()

            india_vix = list(
                filter(lambda x: "VIX" in x["indexSymbol"], indices_data["data"])
            )

            return india_vix[0]["last"]
    except:
        logging.getLogger(__name__).info("Error fecthing INDIA VIX")
    return -1.0


def login(cred_file: str):
    with open(cred_file) as cred_fh:
        cred = json.load(cred_fh)

    client = FivePaisaClient(
        email=cred["email"], passwd=cred["passwd"], dob=cred["dob"], cred=cred
    )
    client.login()

    return client


if __name__ == "__main__":
    # print(get_india_vix())
    client = login("creds.json")
    print(client.positions())
    # client.bo_order(OrderType='S',
    #                 Exchange='N',
    #                 ExchangeType='D',
    #                 ScripCode= 44260, #44222,
    #                 Qty=50,
    #                 LimitPrice=8.05,
    #                 TargetPrice=4.5,
    #                 StopLossPrice=9.5,
    #                 LimitPriceForSL=9.8,
    #                 TrailingSL=0.5,
    #                 TriggerPrice=9.0)

    # TARGET_PRICE is 70% less than the strike price
    # STOP_LOSS_PRICE is 1000% above than the strike price
    strike_price = 8.5
    TARGET_THERSHOLD = 70
    STOP_LOSS_THERSHOLD = 100
    scrip_code = 44260
    TRAILING_STOP_LOSS = 0.5
    QTY = 50
    tag = "test"

    targetPrice = strike_price * (1 - TARGET_THERSHOLD / 100)
    stopLossPrice = strike_price * (1 + STOP_LOSS_THERSHOLD / 100)

    # Stop loss trigger price is 0.5 less than stop loss price
    stopLossTriggerPrice = stopLossPrice - 0.5

    # Limit price
    limitPrice = strike_price

    # Log all prices above
    print("Scrip Code: %s", scrip_code)
    print("Strike Price: %s", strike_price)
    print("Target Price: %s", targetPrice)
    print("Stop Loss Price: %s", stopLossPrice)
    print("Stop Loss Trigger Price: %s", stopLossTriggerPrice)
    print("Limit Price: %s", limitPrice)

    client.bo_order(
        OrderType="S",
        Exchange="N",
        ExchangeType="D",
        ScripCode=scrip_code,
        Qty=QTY,
        LimitPrice=limitPrice,
        TargetPrice=targetPrice,
        StopLossPrice=stopLossTriggerPrice,
        LimitPriceForSL=stopLossPrice,
        TrailingSL=TRAILING_STOP_LOSS,
        RemoteOrderID=tag,
    )
