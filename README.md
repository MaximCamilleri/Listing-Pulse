# UpBit Scalping Strategy 

## Thesis 

UpBit is the largest Korean crypto exchange in the world and a leader in making newly listed assets available in KRW. An analysis of these listings shows that within seconds of each announcement of a new KRW listing from UpBit, the price of the target crypto currency explodes by a minimum of 20%. The goal of this strategy is to capitalize on said gain by minimizing the time between this becoming public knowledge and a trade being placed. This project has 3 main phases:

1. Confirm that the hypothesis is true by analyzing all previous KRW listings
2. Build a robust system that constantly scrapes the UpBit announcement page to identify new assets being listed 
3. Connect the scrapper to a live trading environment to open perps on the target asset 
4. Host the system on AWS to ensure the worker can run continuously when enabled

## Runtime

This project runs as a long-lived worker process:

```bash
python main.py
```

It does not need a web API for the Telegram-to-trade workflow. The process
listens for messages from the configured Telegram channel and passes them to
the interface-layer trading handler.

To run only the scraper and record new notices without taking action on them:

```bash
python scripts/run_scraper.py
```

To place one explicitly requested Binance trade using the configured direction,
quantity, callback rate, and environment:

```bash
python scripts/place_trade.py BTCUSDT
```

The trade command refuses to initialize Binance unless `TRADING_ENABLED=true`.
Both scripts log to stdout and `logs/application.log`; file logs rotate daily at
UTC midnight and are retained for seven days by default.

Container health is represented by `logs/heartbeat`. The application
refreshes it only while Telethon is connected and the event loop remains
responsive. Configure its interval and maximum age with
`HEALTHCHECK_INTERVAL_SECONDS` and `HEALTHCHECK_MAX_AGE_SECONDS`.

## AWS Hosting

The preferred managed hosting option is a single-container ECS Fargate service:

- Build the included `Dockerfile` and publish the image to ECR.
- Run one ECS service with desired count `1` to start the scraper.
- Set desired count `0` to stop the scraper.
- Send container stdout/stderr to CloudWatch Logs.
- Inject Binance credentials from Secrets Manager or SSM Parameter Store.
- Keep `TRADE_ENVIRONMENT=DEMO` and `TRADING_ENABLED=false` until production
  trading has been reviewed.

The lowest-cost option is a small Lightsail Linux instance running `python
main.py` under `systemd`, but that leaves more server maintenance to the owner.

## Tests

- `tests/unit/`: one function or class with collaborators isolated.
- `tests/integration/`: multiple application components working together.
- `tests/e2e/`: a complete workflow with external service boundaries faked.

```bash
python -m unittest discover -s tests/unit -p "test_*.py" -v
python -m unittest discover -s tests/integration -p "test_*.py" -v
python -m unittest discover -s tests/e2e -p "test_*.py" -v
```
