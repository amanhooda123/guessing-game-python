import unittest
from datetime import date
from option_lab.momentum_spreads import candidates,vertical_payoff


class MomentumSpreadTests(unittest.TestCase):
    def test_expiry_payoff_bounded_by_spread_width(self):
        legs=[(('ABC','2025-07-18',95.,'Call'),1),(('ABC','2025-07-18',110.,'Call'),-1)]
        self.assertEqual(vertical_payoff(legs,90),0)
        self.assertEqual(vertical_payoff(legs,105),1000)
        self.assertEqual(vertical_payoff(legs,120),1500)

    def test_rank_uses_prior_momentum_and_has_no_premium_ceiling(self):
        day=date(2025,6,2);rows=[];features={}
        for symbol,mom in [('A',.2),('B',.5)]:
            features[symbol,day]={'spot':100.,'up':True,'dollar_volume':20e6,'momentum_12_1':mom}
            for strike,delta,bid,ask in [(95.,.65,11.,11.2),(110.,.3,3.,3.1)]:
                rows.append({'act_symbol':symbol,'expiration':'2025-08-01','strike':strike,
                             'call_put':'Call','delta':delta,'bid':bid,'ask':ask})
        selected=candidates(rows,day,features)
        self.assertEqual([r['symbol'] for r in selected],['B','A'])
        self.assertGreater((11.2-3)*100,30)

    def test_integer_contract_sizing_changes_cashflows_without_fractional_contracts(self):
        from option_lab.momentum_validation import integer_risk_replay
        rs=[{'legs':[(('A','2025-02-21',100.,'Call'),1)],'entry':'2025-01-02',
             'planned_exit':'2025-02-21','cost':500.,'pnl':100.,'status':'matched'},
            {'legs':[(('A','2025-04-18',100.,'Call'),1)],'entry':'2025-03-03',
             'planned_exit':'2025-04-18','cost':800.,'pnl':-800.,'status':'matched'}]
        p=integer_risk_replay(rs,.01)
        self.assertEqual(p['contracts'],3)
        self.assertEqual(p['realized_pnl'],-600.)
        self.assertAlmostEqual(p['terminal_return_if_fully_resolved'],-.006)


if __name__=='__main__':unittest.main()
