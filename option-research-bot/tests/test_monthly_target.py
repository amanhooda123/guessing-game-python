import unittest
from option_lab.monthly_target import marked_monthly_nav,metrics


class MonthlyTargetTests(unittest.TestCase):
    def test_deposit_does_not_become_profit(self):
        rows=[{'month':'2023-12','net_liquidation_value':100,'complete_position_marks':True},
              {'month':'2024-01','net_liquidation_value':150,'external_flow_at_month_end':50,
               'flow_timing':'month_end','complete_position_marks':True}]
        r=marked_monthly_nav(rows)
        self.assertEqual(r['total_return'],0)
        self.assertFalse(r['historical_average_target_pass'])

    def test_annual_profit_cannot_be_read_as_five_percent_each_month(self):
        r=metrics([.20]+[0.]*11)
        self.assertFalse(r['meets_every_month_target'])
        self.assertEqual(r['months_at_or_above_target'],1)
        self.assertLess(r['geometric_average_monthly_return'],.05)

    def test_unmarked_positions_cannot_pass_the_target(self):
        rows=[{'month':'2023-12','net_liquidation_value':100,'complete_position_marks':False}]
        nav=100
        for year in (2024,2025):
            for month in range(1,13):
                nav*=1.05;rows.append({'month':f'{year}-{month:02}','net_liquidation_value':nav,
                                      'complete_position_marks':False})
        r=marked_monthly_nav(rows)
        self.assertTrue(r['meets_every_month_target'])
        self.assertFalse(r['historical_each_month_target_pass'])

    def test_missing_month_and_intramonth_flows_require_correct_valuation(self):
        with self.assertRaises(ValueError):
            marked_monthly_nav([{'month':'2023-12','net_liquidation_value':100},
                                {'month':'2024-02','net_liquidation_value':110}])
        with self.assertRaises(ValueError):
            marked_monthly_nav([{'month':'2023-12','net_liquidation_value':100},
                                {'month':'2024-01','net_liquidation_value':150,'external_flow_at_month_end':50}])
