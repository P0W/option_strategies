## Author : Prashant Srivastava
import time
from typing import Dict

# current_directory = os.path.dirname(os.path.abspath(__file__))
# # Get the parent directory
# parent_directory = os.path.dirname(current_directory)
# # Add the parent directory to sys.path temporarily
# sys.path.append(parent_directory)

from src.common import live_feed_manager
from src.common import strikes_manager
import json
import logging
from src.clients.client_5paisa import Client as Client5Paisa


def straddle_calculator(res: Dict, user_data: Dict):
    code = res["code"]
    ltp = res["c"]
    target = user_data["target"]
    mtm_loss = user_data["mtm_loss"]
    strikes = user_data["strikes"]
    strikes[code] = ltp
    ## calculate MTM summing the pnl of each leg
    total_pnl = sum(strikes.values())
    logging.info(
        "Total Straddle Preminum: %f %s" % (total_pnl, json.dumps(strikes, indent=2))
    )
    if total_pnl >= target:
        # TARGET ACHEIVED
        logging.info("Target Achieved: %f" % total_pnl)
        # Sqaure off both legs
        logging.info("Squaring off both legs")
        logging.info("Cancelling pending stop loss orders")
        logging.info("Stopping live feed")
        lm.stop()
    elif total_pnl <= mtm_loss:
        # STOP LOSS HIT
        logging.info("Stop Loss Hit: %f" % total_pnl)
        # Sqaure off both legs
        logging.info("Squaring off both legs")
        logging.info("Cancelling pending target orders")
        logging.info("Stopping live feed")
        lm.stop()
    else:
        ## If we waited for 1 minutes and nothing happened, susbscribe to the strike at 50% of the premium
        ## Goofed up strategies just to test the live feed manager for new subscriptions
        if time.time() - user_data["start_time"] > 60:
            logging.info(
                "Waiting for 1 minute, nothing happened, subscribing to the strike at 50% of the premium"
            )
            ## Subscribe to the strike at 50% of the premium
            sm = strikes_manager.StrikesManager(client, {})
            strike = sm.strangle_strikes(total_pnl / 2, "FINNIFTY")
            ## Subscribe to the strike
            lm.subscribe(scrip_code=[strike["ce_code"], strike["pe_code"]])
            ## Update the start time
            user_data["start_time"] = time.time()


## Example usage
if __name__ == "__main__":
    ## Setup logging
    Client5Paisa.configure_logger("DEBUG")
    ## Setup client
    client = Client5Paisa("creds.json")
    client.login()
    ## Get straddle strikes and premium
    sm = strikes_manager.StrikesManager(client, {})
    staddle_strikes = sm.straddle_strikes("FINNIFTY")
    straddle_premium = staddle_strikes["ce_ltp"] + staddle_strikes["pe_ltp"]
    ## Create live feed and start the strategy monitor
    lm = live_feed_manager.LiveFeedManager(client, {})
    lm.monitor(
        scrip_codes=[staddle_strikes["ce_code"], staddle_strikes["pe_code"]],
        on_scrip_data=straddle_calculator,
        user_data={
            "target": straddle_premium * 1.01,
            "mtm_loss": -1 * straddle_premium * 0.99,
            "start_time": time.time(),
            "strikes": {},
        },
    )
