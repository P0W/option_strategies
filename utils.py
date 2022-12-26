## Author : Prashant Srivastava
## Last Modified Date  : Dec 25th, 2022

import requests
import logging


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


if __name__ == "__main__":
    print(get_india_vix())

    import requests
