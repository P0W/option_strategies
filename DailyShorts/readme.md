## Time Trigger - Azure Function

* Function App that executes a strangle strategy closest to 7.0 preminum with stop loss at 55% on both legs at 9:31 am
  1. The respective setup can be configured from [`function.json`](https://github.com/P0W/option_strategies/tree/main/DailyShorts/function.json)
  2. Make sure to add `creds.json` (described on main page) along with the other files
* Note: The strategy is placed only when INDIAVIX <= 20.0
* The logs can be observed on the analytics from "Monitor" tab

