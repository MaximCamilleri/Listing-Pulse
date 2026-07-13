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

It does not need a web API for the scraper-to-trade workflow. The process polls
Upbit, records new notice IDs in memory, and passes new notices to an injected
interface-layer handler. The default handler only places Binance orders when
`TRADING_ENABLED=true`.

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
