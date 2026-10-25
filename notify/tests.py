from django.test import TestCase

# Create your tests here.

# ============================================================
# Bank Mock
# notify/tests.py
# ============================================================

import json

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from django.conf import settings

from util.ChkMacVal import generate_check_mac_value

from .models import VirtualAccount
from .adapters.bank_account_adapter import BankAccountAdapter
from .services.bank_account_service import BankAccountService


# ============================================================
# 【新增】
# Bank Mock ATM 完整測試
# ============================================================

@override_settings(
    BANK_MOCK_BANK_CODE="013",
    BANK_MOCK_EXPIRE_DAYS=3,
    ECPAY_MOCK_PAYMENT_NOTIFY_URL=(
        "{HF_SPACE_ECPAY_MOCK_URL}/gateway/payment_notify/"
    ),
)
class BankAccountFlowTest(TestCase):
    """
    測試 Bank Mock ATM 完整流程。

    測試範圍：

        1. Service 建立 ATM
        2. Adapter 產生銀行代碼
        3. Adapter 產生虛擬帳號
        4. Adapter 產生繳費期限
        5. VirtualAccount 寫入 DB
        6. API create_account
        7. API 回傳 CheckMacValue
        8. simulate_paid
        9. HTTPX callback ECPay Mock
    """

    # ========================================================
    # 【新增】
    # 測試交易編號
    # ========================================================

    merchant_trade_no = (
        "TEST202609120001"
    )

    trade_amt = Decimal("1500.00")

    # ========================================================
    # 【新增】
    # 測試 1
    #
    # Service → Interface → Adapter → DB
    # ========================================================

    def test_service_create_virtual_account(self):
        """
        測試：

            BankAccountService
                ↓
            BankAccountGateway
                ↓
            BankAccountAdapter
                ↓
            VirtualAccount
        """

        # ----------------------------------------------------
        # 【新增】
        # 建立 Service
        #
        # Service 只依賴 Gateway Interface。
        # 實際執行時注入 Adapter。
        # ----------------------------------------------------

        service = BankAccountService(
            gateway=BankAccountAdapter()
        )

        # ----------------------------------------------------
        # 【新增】
        # 建立 ATM 帳號
        # ----------------------------------------------------

        result = service.create_account(
            merchant_trade_no=(
                self.merchant_trade_no
            ),
            trade_amt=self.trade_amt,
        )

        # ----------------------------------------------------
        # 【新增】
        # 驗證 Service 回傳成功
        # ----------------------------------------------------

        self.assertTrue(
            result["status"]
        )

        # ----------------------------------------------------
        # 【新增】
        # 驗證交易編號
        # ----------------------------------------------------

        self.assertEqual(
            result["merchant_trade_no"],
            self.merchant_trade_no,
        )

        # ----------------------------------------------------
        # 【新增】
        # 驗證 Bank Mock 自己產生銀行代碼
        # ----------------------------------------------------

        self.assertEqual(
            result["bank_code"],
            "013",
        )

        # ----------------------------------------------------
        # 【新增】
        # 驗證虛擬帳號確實產生
        # ----------------------------------------------------

        self.assertTrue(
            result["v_account"]
        )

        # ----------------------------------------------------
        # 【新增】
        # 驗證虛擬帳號不是 ECPay Mock 傳進來的
        #
        # 這個測試特別重要。
        # ====================================================
        # Bank Mock 必須自己產生 ATM 資訊。
        # ----------------------------------------------------

        self.assertTrue(
            result["v_account"].startswith("013")
        )

        # ----------------------------------------------------
        # 【新增】
        # 驗證 expire_date
        # ----------------------------------------------------

        self.assertTrue(
            result["expire_date"]
        )

        # ----------------------------------------------------
        # 【新增】
        # 驗證付款狀態
        # ----------------------------------------------------

        self.assertEqual(
            result["payment_status"],
            "atm_created",
        )

        # ----------------------------------------------------
        # 【新增】
        # 確認 DB 真的有資料
        # ----------------------------------------------------

        account = (
            VirtualAccount.objects.get(
                merchant_trade_no=(
                    self.merchant_trade_no
                )
            )
        )

        self.assertEqual(
            account.bank_code,
            "013",
        )

        self.assertEqual(
            account.trade_amt,
            self.trade_amt,
        )

        self.assertEqual(
            account.status,
            "atm_created",
        )

    # ========================================================
    # 【新增】
    # 測試 2
    #
    # 相同 merchant_trade_no 不重複建立帳號
    # ========================================================

    def test_duplicate_create_returns_same_account(self):
        """
        相同 merchant_trade_no 第二次建立時：

            不應該建立第二個 VirtualAccount
            不應該產生新的 v_account
        """

        service = BankAccountService(
            gateway=BankAccountAdapter()
        )

        # ----------------------------------------------------
        # 【新增】
        # 第一次建立
        # ----------------------------------------------------

        first_result = service.create_account(
            merchant_trade_no=(
                self.merchant_trade_no
            ),
            trade_amt=self.trade_amt,
        )

        first_account = (
            first_result["v_account"]
        )

        # ----------------------------------------------------
        # 【新增】
        # 第二次建立
        # ----------------------------------------------------

        second_result = service.create_account(
            merchant_trade_no=(
                self.merchant_trade_no
            ),
            trade_amt=self.trade_amt,
        )

        second_account = (
            second_result["v_account"]
        )

        # ----------------------------------------------------
        # 【新增】
        # 虛擬帳號必須相同
        # ----------------------------------------------------

        self.assertEqual(
            first_account,
            second_account,
        )

        # ----------------------------------------------------
        # 【新增】
        # DB 只能有一筆
        # ----------------------------------------------------

        count = (
            VirtualAccount.objects.filter(
                merchant_trade_no=(
                    self.merchant_trade_no
                )
            ).count()
        )

        self.assertEqual(
            count,
            1,
        )

    # ========================================================
    # 【新增】
    # 測試 3
    #
    # HTTP API → create_account
    # ========================================================

    def test_create_account_api(self):
        """
        測試：

            HTTP POST
                ↓
            views.create_account()
                ↓
            Service
                ↓
            Adapter
                ↓
            DB
        """

        # ----------------------------------------------------
        # 【新增】
        # 建立 POST payload
        #
        # 注意：
        # 這裡刻意不提供：
        #
        # bank_code
        # v_account
        # expire_date
        #
        # 因為這三個資料必須由 Bank Mock 產生。
        # ----------------------------------------------------

        payload = {
            "merchant_trade_no": (
                self.merchant_trade_no
            ),
            "trade_amt": "1500.00",
        }

        # ----------------------------------------------------
        # 【新增】
        # 產生 CheckMacValue
        # ----------------------------------------------------

        payload["CheckMacValue"] = (
            generate_check_mac_value(
                {
                    "merchant_trade_no": (
                        payload[
                            "merchant_trade_no"
                        ]
                    ),
                    "trade_amt": (
                        payload["trade_amt"]
                    ),
                },
                settings.ECPAY_HASH_KEY,
                settings.ECPAY_HASH_IV,
            )
        )

        # ----------------------------------------------------
        # 【新增】
        # 呼叫 API
        # ----------------------------------------------------

        response = self.client.post(
            reverse("create_account"),
            data=json.dumps(payload),
            content_type="application/json",
        )

        # ----------------------------------------------------
        # 【新增】
        # HTTP 200
        # ----------------------------------------------------

        self.assertEqual(
            response.status_code,
            200,
        )

        # ----------------------------------------------------
        # 【新增】
        # JSON response
        # ----------------------------------------------------

        data = response.json()

        # ----------------------------------------------------
        # 【新增】
        # 驗證成功
        # ----------------------------------------------------

        self.assertTrue(
            data["status"]
        )

        # ----------------------------------------------------
        # 【新增】
        # 驗證 ATM 資訊
        # ----------------------------------------------------

        self.assertEqual(
            data["bank_code"],
            "013",
        )

        self.assertTrue(
            data["v_account"]
        )

        self.assertTrue(
            data["expire_date"]
        )

        self.assertEqual(
            data["payment_status"],
            "pending",
        )

        # ----------------------------------------------------
        # 【新增】
        # 驗證 DB
        # ----------------------------------------------------

        self.assertTrue(
            VirtualAccount.objects.filter(
                merchant_trade_no=(
                    self.merchant_trade_no
                )
            ).exists()
        )

    # ========================================================
    # 【新增】
    # 測試 4
    #
    # ATM simulate_paid
    # ========================================================

    @patch(
        "notify.adapters.bank_account_adapter.httpx.post"
    )
    def test_simulate_paid(
        self,
        mock_httpx_post,
    ):
        """
        測試：

            simulate_paid
                ↓
            Service
                ↓
            Adapter
                ↓
            DB status = paid
                ↓
            HTTPX
                ↓
            ECPay Mock
        """

        # ----------------------------------------------------
        # 【新增】
        # 先建立 ATM 帳號
        # ----------------------------------------------------

        service = BankAccountService(
            gateway=BankAccountAdapter()
        )

        service.create_account(
            merchant_trade_no=(
                self.merchant_trade_no
            ),
            trade_amt=self.trade_amt,
        )

        # ----------------------------------------------------
        # 【新增】
        # 模擬 ECPay Mock 回應
        #
        # 測試時不真的打：
        #
        # http://127.0.0.1:8001
        #
        # ----------------------------------------------------

        mock_httpx_post.return_value.status_code = 200

        mock_httpx_post.return_value.json.return_value = {
            "status": "success"
        }

        mock_httpx_post.return_value.text = (
            '{"status":"success"}'
        )

        # ----------------------------------------------------
        # 【新增】
        # 執行付款成功
        # ----------------------------------------------------

        result = service.simulate_paid(
            self.merchant_trade_no
        )

        # ----------------------------------------------------
        # 【新增】
        # 驗證 Service 成功
        # ----------------------------------------------------

        self.assertTrue(
            result["status"]
        )

        # ----------------------------------------------------
        # 【新增】
        # 驗證 DB 狀態
        # ----------------------------------------------------

        account = (
            VirtualAccount.objects.get(
                merchant_trade_no=(
                    self.merchant_trade_no
                )
            )
        )

        self.assertEqual(
            account.status,
            "paid",
        )

        # ----------------------------------------------------
        # 【新增】
        # 確認 HTTPX 確實被呼叫
        # ----------------------------------------------------

        mock_httpx_post.assert_called_once()

        # ----------------------------------------------------
        # 【新增】
        # 取得 HTTPX 實際傳送內容
        # ----------------------------------------------------

        call_args = (
            mock_httpx_post.call_args
        )

        sent_payload = (
            call_args.kwargs["json"]
        )

        # ----------------------------------------------------
        # 【新增】
        # 驗證 callback
        # ----------------------------------------------------

        self.assertEqual(
            sent_payload[
                "merchant_trade_no"
            ],
            self.merchant_trade_no,
        )

        self.assertEqual(
            sent_payload["bank_code"],
            "013",
        )

        self.assertEqual(
            sent_payload["status"],
            "paid",
        )

        # ----------------------------------------------------
        # 【新增】
        # 必須有 CheckMacValue
        # ----------------------------------------------------

        self.assertIn(
            "CheckMacValue",
            sent_payload,
        )

    # ========================================================
    # 【新增】
    # 測試 5
    #
    # ATM simulate_failed
    # ========================================================

    @patch(
        "notify.adapters.bank_account_adapter.httpx.post"
    )
    def test_simulate_failed(
        self,
        mock_httpx_post,
    ):
        """
        測試：

            simulate_failed
                ↓
            Service
                ↓
            Adapter
                ↓
            HTTPX
                ↓
            ECPay Mock
        """

        # ----------------------------------------------------
        # 【新增】
        # 建立 ATM
        # ----------------------------------------------------

        service = BankAccountService(
            gateway=BankAccountAdapter()
        )

        service.create_account(
            merchant_trade_no=(
                self.merchant_trade_no
            ),
            trade_amt=self.trade_amt,
        )

        # ----------------------------------------------------
        # 【新增】
        # 模擬 ECPay Mock response
        # ----------------------------------------------------

        mock_httpx_post.return_value.status_code = 200

        mock_httpx_post.return_value.json.return_value = {
            "status": "success"
        }

        mock_httpx_post.return_value.text = (
            '{"status":"success"}'
        )

        # ----------------------------------------------------
        # 【新增】
        # 執行 failed callback
        # ----------------------------------------------------

        result = service.simulate_failed(
            self.merchant_trade_no
        )

        # ----------------------------------------------------
        # 【新增】
        # 驗證 callback 成功
        # ----------------------------------------------------

        self.assertTrue(
            result["status"]
        )

        # ----------------------------------------------------
        # 【新增】
        # 取得 HTTPX payload
        # ----------------------------------------------------

        call_args = (
            mock_httpx_post.call_args
        )

        sent_payload = (
            call_args.kwargs["json"]
        )

        # ----------------------------------------------------
        # 【新增】
        # 驗證 status = failed
        #
        # 注意：
        # 這只是 callback 給 ECPay Mock。
        #
        # VirtualAccount Model 目前沒有 failed。
        # ----------------------------------------------------

        self.assertEqual(
            sent_payload["status"],
            "failed",
        )

        # ----------------------------------------------------
        # 【新增】
        # 必須有 CheckMacValue
        # ----------------------------------------------------

        self.assertIn(
            "CheckMacValue",
            sent_payload,
        )

        # ----------------------------------------------------
        # 【新增】
        # Bank DB 狀態仍然維持 atm_created
        # ----------------------------------------------------

        account = (
            VirtualAccount.objects.get(
                merchant_trade_no=(
                    self.merchant_trade_no
                )
            )
        )

        self.assertEqual(
            account.status,
            "atm_created",
        )

    # ========================================================
    # 【新增】
    # 測試 6
    #
    # 不允許付款後再次付款
    # ========================================================

    @patch(
        "notify.adapters.bank_account_adapter.httpx.post"
    )
    def test_cannot_pay_twice(
        self,
        mock_httpx_post,
    ):
        """
        已付款的 ATM 帳號不能再次付款。
        """

        service = BankAccountService(
            gateway=BankAccountAdapter()
        )

        # ----------------------------------------------------
        # 【新增】
        # 建立 ATM
        # ----------------------------------------------------

        service.create_account(
            merchant_trade_no=(
                self.merchant_trade_no
            ),
            trade_amt=self.trade_amt,
        )

        # ----------------------------------------------------
        # 【新增】
        # Mock ECPay response
        # ----------------------------------------------------

        mock_httpx_post.return_value.status_code = 200

        mock_httpx_post.return_value.json.return_value = {
            "status": "success"
        }

        # ----------------------------------------------------
        # 【新增】
        # 第一次付款
        # ----------------------------------------------------

        service.simulate_paid(
            self.merchant_trade_no
        )

        # ----------------------------------------------------
        # 【新增】
        # 第二次付款應該失敗
        # ----------------------------------------------------

        with self.assertRaises(ValueError):

            service.simulate_paid(
                self.merchant_trade_no
            )

    # ========================================================
    # 【新增】
    # 測試 7
    #
    # CheckMacValue 錯誤
    # ========================================================

    def test_create_account_invalid_mac(self):
        """
        錯誤 MAC 不允許建立 ATM。
        """

        payload = {
            "merchant_trade_no": (
                self.merchant_trade_no
            ),
            "trade_amt": "1500.00",
            "CheckMacValue": "WRONG_MAC",
        }

        response = self.client.post(
            reverse("create_account"),
            data=json.dumps(payload),
            content_type="application/json",
        )

        # ----------------------------------------------------
        # 【新增】
        # 必須拒絕
        # ----------------------------------------------------

        self.assertEqual(
            response.status_code,
            400,
        )

        # ----------------------------------------------------
        # 【新增】
        # DB 不應該產生帳號
        # ----------------------------------------------------

        self.assertFalse(
            VirtualAccount.objects.filter(
                merchant_trade_no=(
                    self.merchant_trade_no
                )
            ).exists()
        )

    # ========================================================
    # 【新增】
    # 測試 8
    #
    # 缺少 merchant_trade_no
    # ========================================================

    def test_create_account_missing_trade_no(self):
        """
        缺少 merchant_trade_no 時拒絕建立。
        """

        payload = {
            "trade_amt": "1500.00",
        }

        payload["CheckMacValue"] = (
            generate_check_mac_value(
                payload,
                settings.ECPAY_HASH_KEY,
                settings.ECPAY_HASH_IV,
            )
        )

        response = self.client.post(
            reverse("create_account"),
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(
            response.status_code,
            400,
        )

    # ========================================================
    # 【新增】
    # 測試 9
    #
    # 缺少 trade_amt
    # ========================================================

    def test_create_account_missing_trade_amount(self):
        """
        缺少 trade_amt 時拒絕建立。
        """

        payload = {
            "merchant_trade_no": (
                self.merchant_trade_no
            ),
        }

        payload["CheckMacValue"] = (
            generate_check_mac_value(
                payload,
                settings.ECPAY_HASH_KEY,
                settings.ECPAY_HASH_IV,
            )
        )

        response = self.client.post(
            reverse("create_account"),
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(
            response.status_code,
            400,
        )