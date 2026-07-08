# UpBit Scalping Strategy 

## Thesis 

UpBit is the largest Korean crypto exchange in the world and a leader in making newly listed assets available in KRW. An analysis of these listings shows that within seconds of each announcement of a new KRW listing from UpBit, the price of the target crypto currency explodes by a minimum of 20%. The goal of this strategy is to capitalize on said gain by minimizing the time between this becoming public knowledge and a trade being placed. This project has 3 main phases:

1. Confirm that the hypothesis is true by analyzing all previous KRW listings
2. Build a robust system that constantly scrapes the UpBit announcement page to identify new assets being listed 
3. Connect the scrapper to a live trading environment to open perps on the target asset 
4. Host the system on an EC2 instance to ensure 100% uptime