import unittest
from datetime import datetime,timedelta,timezone
from option_lab.stocks_in_play import select_stocks,select_options


class StocksInPlayTests(unittest.TestCase):
    def fixture(self):
        daily=[];bars=[]
        for n in range(15):
            d=datetime(2024,1,2,tzinfo=timezone.utc)+timedelta(days=n)
            daily.append({'symbol':'ABC','date':d.date().isoformat(),'high':102.,'low':99.,'close':100.,'volume':2e6})
            bars.append({'symbol':'ABC','datetime':d.replace(hour=14,minute=30).isoformat(),
                         'open':100.,'high':101.,'low':99.,'close':100.5,'volume':1000.})
        bars += [{'symbol':'ABC','datetime':'2024-01-18T14:30:00Z','open':100.,'high':101.,'low':99.,'close':100.5,'volume':3000.},
                 {'symbol':'ABC','datetime':'2024-01-18T14:35:00Z','open':100.5,'high':102.,'low':100.,'close':101.5,'volume':4000.}]
        return bars,daily

    def test_incomplete_bar_cannot_generate_breakout(self):
        bars,daily=self.fixture()
        self.assertEqual(select_stocks(bars,daily,'2024-01-18T14:39:59Z'),[])
        rs=select_stocks(bars,daily,'2024-01-18T14:40:00Z')
        self.assertEqual(rs[0]['direction'],'call')
        self.assertEqual(rs[0]['relative_opening_volume'],3.)

    def test_trade_bar_without_bid_ask_cannot_become_an_option_fill(self):
        bars,daily=self.fixture();stocks=select_stocks(bars,daily,'2024-01-18T14:40:00Z')
        r=select_options(stocks,[{'underlying_symbol':'ABC','close':2.}])
        self.assertIsNone(r['research_candidates'][0]['contract'])
        self.assertEqual(r['action'],'NO TRADE')

    def test_quote_before_signal_cannot_be_retroactive_entry(self):
        bars,daily=self.fixture();stocks=select_stocks(bars,daily,'2024-01-18T14:40:00Z')
        q={'underlying_symbol':'ABC','option_symbol':'ABC240216C00100000','right':'call',
           'expiration':'2024-02-16','delta':.6,'bid':1.9,'ask':2.,'bid_size':5,'ask_size':5,
           'quote_timestamp':'2024-01-18T14:39:00Z'}
        r=select_options(stocks,[q]);self.assertIsNone(r['research_candidates'][0]['contract'])

    def test_opening_rank_is_fixed_before_later_breakouts(self):
        bars,daily=self.fixture()
        other_bars=[{**r,'symbol':'XYZ'} for r in bars]
        other_daily=[{**r,'symbol':'XYZ'} for r in daily]
        for r in other_bars:
            if r['datetime']=='2024-01-18T14:30:00Z':r['volume']=6000.
            if r['datetime']=='2024-01-18T14:35:00Z':r['close']=100.5
        # Highest opening-volume stock has no breakout; do not replace it with ABC.
        self.assertEqual(select_stocks(bars+other_bars,daily+other_daily,
                                      '2024-01-18T14:40:00Z',limit=1),[])
