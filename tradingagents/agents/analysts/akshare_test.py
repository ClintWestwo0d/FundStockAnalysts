import akshare as ak
symbol = '630002'
# 尝试获取个股信息
stock_info = ak.fund_individual_basic_info_xq(symbol=symbol)

dic = stock_info.set_index('item').to_dict()['value']

fund_individual_detail_hold_xq_df = ak.fund_individual_detail_hold_xq(symbol="002804")

print(stock_info)
