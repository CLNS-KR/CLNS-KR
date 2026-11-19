import unittest

from import_compliance import api, cosmetic_ingredients, tariff_fta
from import_compliance.store import Store


class TariffFtaTests(unittest.TestCase):
    def test_japan_has_no_bilateral_fta(self):
        res = tariff_fta.assess_tariff_fta(product="일본 화장품 세럼", origin="일본", purpose="resale")
        self.assertFalse(res["fta"]["has_fta"])
        self.assertIn("6.5%", res["base_rate_hint"])
        self.assertIn("사업자 통관", res["duty_free_note"])

    def test_us_self_use_limit_200(self):
        res = tariff_fta.assess_tariff_fta(product="미국 블루투스 스피커", origin="미국", purpose="self_use")
        self.assertTrue(res["fta"]["has_fta"])
        self.assertIn("$200", res["duty_free_note"])

    def test_vietnam_apparel_fta(self):
        res = tariff_fta.assess_tariff_fta(product="베트남산 티셔츠", hs_code="6109100000", origin="베트남")
        self.assertTrue(res["fta"]["has_fta"])
        self.assertIn("13%", res["base_rate_hint"])


class CosmeticIngredientsTests(unittest.TestCase):
    def test_prohibited_hydroquinone_and_bimatoprost(self):
        res = cosmetic_ingredients.screen_cosmetic_ingredients(
            "Water, Glycerin, Hydroquinone, Bimatoprost, Phenoxyethanol"
        )
        self.assertEqual(res["verdict"], "blocked_risk")
        self.assertEqual(len(res["prohibited"]), 2)
        self.assertEqual(len(res["restricted"]), 1)

    def test_restricted_only(self):
        res = cosmetic_ingredients.screen_cosmetic_ingredients("Water, Salicylic Acid, Niacinamide")
        self.assertEqual(res["verdict"], "review_required")
        self.assertEqual(len(res["prohibited"]), 0)
        self.assertEqual(len(res["restricted"]), 2)

    def test_assess_import_case_integrates_tariff_cosmetic_and_summary_en(self):
        store = Store(":memory:")
        out = api.tool_assess_import_case(
            {
                "query": "일본산 속눈썹 영양제 판매용",
                "facts": {
                    "origin": "일본",
                    "purpose": "resale",
                    "cosmetic_ingredients": "Water, Bimatoprost, Panthenol",
                },
            },
            store=store,
            client_id="test",
            tier="free",
        )
        res = out["result"]
        self.assertIn("tariff_fta", res)
        self.assertEqual(res["tariff_fta"]["origin"], "일본")
        self.assertIn("cosmetic_screening", res)
        self.assertEqual(len(res["cosmetic_screening"]["prohibited"]), 1)
        self.assertEqual(res["verdict"]["code"], "check_likely")
        self.assertIn("summary_en", res)
        self.assertTrue(res["summary_en"]["has_prohibited_cosmetic_ingredient"])


if __name__ == "__main__":
    unittest.main()
