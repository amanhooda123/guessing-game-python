import unittest
from datetime import date
from option_lab.event_study import entry_cashflow,exit_cashflow,settle_put,put_portfolio,crossed_split,split_factor


class EventStudyTests(unittest.TestCase):
    def test_calendar_cashflows_use_long_ask_short_bid_then_reverse(self):
        legs=[(('ABC','2025-07-18',100.,'Call'),1),
              (('ABC','2025-06-20',100.,'Call'),-1)]
        q=[{'bid':5.,'ask':5.2},{'bid':3.,'ask':3.2}]
        entry=entry_cashflow(legs,q,fee=.65,slip=.01,fx=.015)
        self.assertAlmostEqual(entry,-5.2*100*1.01*1.015+3*100*.99*.985-1.3)
        out=exit_cashflow(legs,q,fee=.65,slip=.01,fx=.015)
        self.assertAlmostEqual(out,5*100*.99*.985-3.2*100*1.01*1.015-1.3)
        self.assertLess(entry+out,0)

    def test_put_assignment_includes_full_stock_loss_not_just_premium(self):
        key=('ABC','2025-07-18',100.,'Put')
        self.assertEqual(settle_put(key,150,110),150)
        self.assertAlmostEqual(settle_put(key,150,70),150+7000*.999-10000-.65)
        self.assertAlmostEqual(settle_put(key,150,70,fx=.015),150+7000*.999*.985-10150-.65)

    def test_collateral_and_single_symbol_prevent_overlapping_free_capital(self):
        def record(sym,entry,exit_,pnl,status='matched'):
            return {'legs':[((sym,'2025-07-18',100.,'Put'),-1)],'entry':entry,
                    'planned_exit':exit_,'cost':10000.,'pnl':pnl,'status':status}
        records=[record('A','2025-01-02','2025-02-01',200),
                 record('A','2025-01-03','2025-02-01',1000),
                 record('B','2025-01-03','2025-02-01',-500),
                 record('C','2025-01-03','2025-02-01',200)]
        p=put_portfolio(records,capital=20000,allocation=.60)
        self.assertEqual(p['fills'],2)
        self.assertAlmostEqual(p['terminal_return_if_fully_resolved'],-.015)
        self.assertEqual(p['skipped']['symbol_already_held'],1)
        self.assertEqual(p['skipped']['collateral'],1)

    def test_unresolved_trade_does_not_become_a_terminal_profit(self):
        r={'legs':[(('A','2025-07-18',100.,'Put'),-1)],'entry':'2025-01-02',
           'planned_exit':'2025-02-01','cost':10000.,'status':'missing_underlying_exit'}
        p=put_portfolio([r],capital=20000,allocation=.60)
        self.assertIsNone(p['terminal_return_if_fully_resolved'])
        self.assertEqual(p['unresolved_full_loss_equity'],10000)

    def test_split_boundary(self):
        splits={('ABC',date(2025,2,1)):10}
        self.assertTrue(crossed_split('ABC',date(2025,1,1),date(2025,2,1),splits))
        self.assertFalse(crossed_split('ABC',date(2025,2,1),date(2025,2,3),splits))

    def test_zero_or_missing_split_factor_cannot_adjust_stock_history(self):
        self.assertIsNone(split_factor({'to_factor':'0.00000','for_factor':'0.00000'}))
        self.assertIsNone(split_factor({'to_factor':None,'for_factor':'1'}))
        self.assertEqual(split_factor({'to_factor':'10','for_factor':'1'}),10.)

    def test_assignment_next_open_does_not_redecide_assignment_after_rebound(self):
        from option_lab.event_validation import next_open_put
        r={'legs':[(('ABC','2025-07-18',100.,'Put'),-1)],
           'entry_quotes':[{'bid':1.5,'ask':1.6}], 'entry':'2025-06-20',
           'status':'matched','exit':'2025-07-18','planned_exit':'2025-07-18',
           'exit_spot':95.,'cost':10000.}
        expiry=date(2025,7,18);monday=date(2025,7,21)
        out=next_open_put(r,{('ABC',monday):105.},{expiry:monday},{})
        premium=1.5*100*.99-.65
        self.assertAlmostEqual(out['pnl'],premium+10500*.999-.65-10000)
        self.assertEqual(out['planned_exit'],'2025-07-21')

    def test_future_expiry_cannot_be_clipped_into_current_year_profit(self):
        from unittest.mock import patch
        import pyarrow as pa
        from option_lab.event_study import run
        day=date(2025,12,30);entry=date(2025,12,31)
        key=('PLTR','2026-02-20',155.,'Put')
        stream=[(day,[]),(entry,[])]
        selection={'cash_secured_put':{'legs':((key,-1),),'event':None}}
        with patch('pyarrow.parquet.read_table',return_value=pa.table({'date':['2025-12-30','2025-12-31']})), \
             patch('option_lab.event_study.stock_context',return_value=({}, {}, {})), \
             patch('option_lab.event_study._dates_and_rows',return_value=iter(stream)), \
             patch('option_lab.event_study.selections',return_value=selection):
            result=run(['mock'], 'mock',[],[])
        self.assertEqual(result['strategies']['cash_secured_put']['2025']['selected'],0)


if __name__=='__main__':unittest.main()
