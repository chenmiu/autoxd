#-*- coding:utf-8 -*-
# Copyright (c) Kang Wang. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
# QQ: 1764462457


"""基于成本交易
"""
from __future__ import print_function
import sys
import qjjy
import pd_help
import myredis, agl, help, stock, backtest_policy, ui,account as ac, sign_observation as so, pattern_recognition as pr
if sys.version > '3':
    import stock_pinyin3 as jx
else:
    import stock_pinyin as jx
from backtest_runner import BackTestPolicy
#import tushare as ts
import tc
import datetime
import pandas as pd
import numpy as np
import talib
from pypublish import publish

class Strategy_Boll_Pre(qjjy.Strategy):
    """boll分仓"""
    class enum:
        """保存上一次的交易状态"""
        nothing = -1
        boll_up = 0
        boll_up_mid = 1
        boll_mid = 2
        boll_down_mid = 3
        boll_down = 4
        zz_up = 5
        zz_down = 6
        zz_hui_bu = 7	#回补
    def setParams(self, *args, **kwargs):
        self.is_tick_report = False
        self.trade_num_use_money_percent = 0.015	    #区间交易数量
        self.trade_num_ratio = 2    #二档对于一档的倍数
        self.trade_ratio = 0.1    #区间的比率
        self.lowerhold = 0.05	    #首仓使用的资金
        self.trade_four=[-1, 0.1]
        #self.canwei = [1,2,2,5]
        self.is_compensate = False   #仓位补偿
        #必须实现
        for k, v in kwargs.iteritems():
            setattr(self, k, v)
        self.min_sell_price = 1000
        self.max_buy_price = 0
        self.trade_status = self.enum.nothing
    def AllowCode(self, code):
        #return False
        #self._log(code)
        return code == '300033'
    def OnFirstRun(self):
        """回测调用函数， 在第一个bar时调用， 先建立底仓"""
        assert(self.is_backtesting)
        code = self.data.get_code()
        df_hisdat = self.data.get_hisdat(code)
        #这里取不到开盘价， 用昨收盘代替
        price = float(df_hisdat.iloc[-1]['c'])
        account = self._getAccount()
        account_mgr = ac.AccountMgr(account, price, code)
        num = ac.ShouShu(account_mgr.total_money()*self.lowerhold/price)
        #account._buy(code, price, num, self.getCurTime())    
    def Run(self):
        """
        """
        #self._log('Strategy_Boll_Pre')

        #以下为交易测试
        code = self.data.get_code()	#当前策略处理的股票
        self.code = code
        if not self.is_backtesting and not self.AllowCode(code):
            return

        self._log(self.getCurTime())
        df_hisdat = self.data.get_hisdat(code)	#日k线
        df_five_hisdat = self.data.get_hisdat(code, dtype='5min')	#5分钟k线
        if len(df_five_hisdat)<=30:
            return

        account = self._getAccount()	#获取交易账户
        price = float(df_five_hisdat.tail(1)['c'])    #当前股价
        closes = df_hisdat['c']
        yestoday_close = closes[-2]	    #昨日收盘价
        account_mgr = ac.AccountMgr(account, price, code)
        trade_num = ac.ShouShu(account_mgr.init_money()*self.trade_num_use_money_percent/price)

        # 信号计算
        four = stock.FOUR(df_hisdat['c'])[-1]
        upper, middle, lower = stock.TDX_BOLL(df_five_hisdat['c'])
        highs, lows, closes = df_five_hisdat['h'], df_five_hisdat['l'], df_five_hisdat['c']
        adx = stock.TDX_ADX(highs, lows, closes)
        adx = adx[-1]
        self._log('boll : %.2f,%.2f,%.2f'%(upper[-1], middle[-1],lower[-1]))
        boll_w = abs(upper[-1]-lower[-1])/middle[-1]*100
        zz_up = stock.ZigZag(upper[-60:], percent=.1)
        zz_low = stock.ZigZag(lower[-60:], percent=0.1)

        boll_poss = [
            upper[-1],
         (upper[-1] - middle[-1])/2+middle[-1],
         middle[-1],
         (middle[-1] - lower[-1])/2+lower[-1],	     
         lower[-1],
        ]
        self._log('boll_poss: %.2f, %.2f boll_w=%.2f adx=%.2f'%(boll_poss[0], boll_poss[1], boll_w, adx))

        #帐户信息
        pre_price = account_mgr.last_chengjiao_price(is_sell=-1) #上一个成交的价位
        pre_buy_price = account_mgr.last_chengjiao_price(is_sell=0)
        if np.isnan(pre_buy_price) :
            pre_buy_price = pre_price
        pre_sell_num = account_mgr.last_chengjiao_num()  #上次的成交数量
        pre_pre_price = account_mgr.last_chengjiao_price(index=-2)
        sell_count = account_mgr.queryTradeCount(1)
        buy_count = account_mgr.queryTradeCount(0)
        chen_ben = account_mgr.get_BuyAvgPrice()    #买入成本
        yin_kui = account_mgr.yin_kui()		    #盈亏成本
        canwei = account_mgr.getCurCanWei()

        #信号判断
        num = 0
        order = 0
        if so.assemble(
            price > boll_poss[1]*1.001,
                        price > pre_price*(1+self.trade_ratio),
                       #price > boll_poss[2],
                       #price > self.max_buy_price*(1+self.trade_ratio),
                       boll_w > 3.5,
                       #adx > 45,
                       #sell_count < 2,
                       #pr.horizontal(df_five_hisdat),
                       #0,
                       ):
            num = trade_num
            order = 1
        if so.assemble(price > boll_poss[0] , 
                       price > pre_price*(1+self.trade_ratio),
                       #price > self.max_buy_price*(1+self.trade_ratio), 
                       boll_w > 3.5,
                       #adx>60,
                       #four > self.trade_four[1],
                       #sell_count < 2,
                       #self.trade_status == self.enum.nothing,
                       #0,
                       ):
            if pre_sell_num>0:
                num = (pre_sell_num * self.trade_num_ratio)
            else:
                num = ac.ShouShu(account_mgr.getCurCanWei() * 0.5)
            order = 1
        if so.assemble(
            price < boll_poss[-2]*0.999,
            price < pre_price*(1-self.trade_ratio),
                       #price < boll_poss[2],
                       #price < self.min_sell_price*(1-0.03),
                       boll_w > 3.5,
                       adx>75,
                       #buy_count < 2,
                       #pr.horizontal(df_five_hisdat),
                       #0,
                       ):
            num = trade_num
            order = 0
        if so.assemble(price < boll_poss[-1],
                       price < pre_buy_price*(1-self.trade_ratio),
                       #price < self.min_sell_price*(1-0.03),
                       boll_w > 3.5,
                       #buy_count < 2,
                       #self.trade_status == self.enum.nothing,
                       adx>80,
                       #four < self.trade_four[0],
                       #0,
                       ):
            #加仓买入
            num = account_mgr.getCurCanWei() * self.trade_num_ratio
            order = 0
        if num>0:
            self.order(order, code, price, num)
        #建首仓
        if so.assemble(four< self.trade_four[0],
                       boll_w>4,
                       adx>70,
                       price < boll_poss[-2]*0.999,
                       canwei == 0,
                       ):
            num = ac.ShouShu(account_mgr.total_money()*self.lowerhold/price)
            bSell = 0
            self.order(bSell, code, price, num)

        #tick report
        if self.is_backtesting and self.is_tick_report:
            self._getAccount().TickReport(df_five_hisdat, 'win')
        return	

    #----------------------------------------------------------------------
    def _getAccount(self):
        if self.is_backtesting:
            return self.data.account	#LocalAccount
        return tc.TcAccount(self.data)  
    def _compensate(self, num, bSell, code):
        """回归初始仓位, 补偿损失的仓位, 在大涨或大跌时调用
        return: int 新的交易数量"""
        account = self._getAccount()
        account_mgr = ac.AccountMgr(account, np.nan, code)
        #获取初始仓位
        initCanWei = account_mgr.getInitCanWei()
        #获取当前仓位
        curCanWei = account_mgr.getCurCanWei()
        if bSell:
            if curCanWei - num > initCanWei:
                num = curCanWei - initCanWei
                print(self.getCurTime(), '补偿数%d'%num, bSell)
        else:
            if curCanWei + num < initCanWei:
                num = initCanWei - curCanWei
                print(self.getCurTime(), '补偿数%d'%num, bSell)
        return num

    def order(self, bSell, code, price, num):
        """判断同一区间是否已经有委托, 同时计算区间交易部分的买入均价
        bSell: int 不能使用boolean
        return True 下单， 
        return False 但同一区域已经下单的， 放弃下单"""
        assert(not isinstance(bSell, bool))

        #看是否已经下单
        df = self._getAccount().WeiTuoList()
        if len(df) > 0:
            df = df[df['证券代码']==code]
            df = df[df['买0卖1']==str(bSell)]
            df = df[df['状态说明'] == tc.TCAccountCache.enum.yibao]
            bHaveWeiTuo = False
            chajia = self.trade_ratio/2
            for p in df['委托价格']:
                p = float(p)
                if abs(price - p)/price < chajia:
                    bHaveWeiTuo = True
                    return False

        return self._getAccount().Order(bSell, code, price, num)


def Run(codes, task_id=0):
    #agl.LOG('sdf中')
    #codes = ['300033']
    def setParams(s):
        if 0: s = Strategy_Boll
        s.setParams(
            pl=publish.Publish(),
        )
    backtest_policy.test_strategy(codes, Strategy_Boll_Pre, setParams,
                                  start_day='2018-3-26', end_day='',
                                  #start_day='2017-12-2', end_day='2017-12-13', 
                                  mode=BackTestPolicy.enum.hisdat_mode|BackTestPolicy.enum.hisdat_five_mode,
                                  )
import unittest
class mytest(unittest.TestCase):
    def test_strategy(self):
        main_run()
def main_run():        
        codes = stock.DataSources.getCodes()
        cpu_num = 5
        codes = stock.get_codes(stock.myenum.randn, cpu_num)
        agl.startDebug()
        if agl.IsDebug():
            codes = [jx.KYWL]
        exec(agl.Marco.IMPLEMENT_MULTI_PROCESS)

if __name__ == "__main__":
    #unittest.main()	    
    main_run()