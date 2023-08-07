*Daily strangle, expiry straddle on weekly contracts (NIFTY,BANKNIFTY AND FINNIFTY)*
---

Prerequisites:
* 5paisa Brokerage Account
* Python 3.9+
* 5paisa python SDK
---

```
usage: daily_short.py [-h] [--creds CREDS] [-s] [--monitor-target MONITOR_TARGET] [-cp CLOSEST_PREMIUM] [-sl STOP_LOSS_FACTOR] [-q QUANTITY] [--index INDEX] [--tag TAG] [--log-level LOG_LEVEL] [--pnl]
                      [--strangle] [--straddle]

options:
  -h, --help            show this help message and exit
  --creds CREDS         Credentials file for login to 5paisa account
  -s, --show-strikes-only
                        Show strikes only, do not place order
  --monitor-target MONITOR_TARGET
                        Keep polling for given target amount
  -cp CLOSEST_PREMIUM, --closest_premium CLOSEST_PREMIUM
                        Search the strangle strikes for provided closest premium
  -sl STOP_LOSS_FACTOR, --stop_loss_factor STOP_LOSS_FACTOR
                        Percent above the placed price for stop loss
  -q QUANTITY, --quantity QUANTITY
                        Quantity to short for Nifty (Lot size =50), for 1 lot say 50
  --index INDEX         Index to trade (NIFTY/BANKNIFTY)
  --tag TAG             Tag to print status of last order for given tag, if combined with --monitor_target it polls the position for given tag
  --log-level LOG_LEVEL
                        Log level (INFO|DEBUG) (default = DEBUG)
  --pnl                 Show current PNL
  --strangle            Place Strangle
  --straddle            Place Straddle
  ```
