import akshare as ak
print("akshare version:", ak.__version__)
print("Searching for sina etf functions...")
for attr in dir(ak):
    if 'sina' in attr and 'etf' in attr:
        print(attr)
    elif 'sina' in attr and 'fund' in attr:
        print(attr)
