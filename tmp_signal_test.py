from engine import analyze_pair
from config import ALL_FREE_PAIRS
pair = ALL_FREE_PAIRS[0]
print('Testing', pair['name'], pair['symbol'])
res = analyze_pair(pair, tier='public')
print('Result:', res)
