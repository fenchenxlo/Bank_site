# ============================================================
# Bank Mock
# notify/adapters/bank_account_adapter.py
# ============================================================

import hmac
import logging
import random

import httpx

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from util.ChkMacVal import (
    generate_check_mac_value,
)

from ..models import VirtualAccount

from ..interfaces.bank_account_gateway import (
    BankAccountGateway,
)


logger = logging.getLogger(__name__)


class BankAccountAdapter(BankAccountGateway):
    """
    【本次修改】

    Bank Mock ATM Adapter。

    Adapter 負責：

        1. 驗證 ECPay Mock → Bank Mock 的 CheckMacValue
        2. 產生 bank_code
        3. 產生 v_account
        4. 產生 expire_date
        5. 寫入 VirtualAccount
        6. 查詢 VirtualAccount
        7. 更新 VirtualAccount
        8. HTTPX 通知 ECPay Mock

    ============================================================
    Service 不負責
    ============================================================

        ❌ HTTPX
        ❌ CheckMacValue 計算
        ❌ CheckMacValue 驗證

    ============================================================
    最終架構
    ============================================================

        View
          ↓
        BankAccountService
          ↓
        BankAccountGateway
          ↓
        BankAccountAdapter
          ↓
        VirtualAccount / HTTPX / CheckMacValue
    """

    # ========================================================
    # 初始化
    # ========================================================

    def __init__(self):

        # ----------------------------------------------------
        # 【保留】
        # Bank Code
        # ----------------------------------------------------

        self.bank_code = getattr(
            settings,
            "BANK_MOCK_BANK_CODE",
            "013",
        )

        # ----------------------------------------------------
        # 【保留】
        # ATM 有效期限
        # ----------------------------------------------------

        self.expire_days = getattr(
            settings,
            "BANK_MOCK_EXPIRE_DAYS",
            3,
        )

        # ----------------------------------------------------
        # 【保留】
        # ECPay Mock callback URL
        # ----------------------------------------------------

        self.ecpay_mock_url = getattr(
            settings,
            "ECPAY_MOCK_PAYMENT_NOTIFY_URL",
            "",
        )

        # ----------------------------------------------------
        # 【保留】
        # 如果沒有直接設定 callback URL，
        # 使用 ECPay Mock Base URL 組合。
        # ----------------------------------------------------

        if not self.ecpay_mock_url:

            ecpay_mock_base_url = getattr(
                settings,
                "HF_SPACE_ECPAY_MOCK_URL",
                "",
            )

            if ecpay_mock_base_url:

                self.ecpay_mock_url = (
                    f"{ecpay_mock_base_url.rstrip('/')}"
                    "/gateway/payment_notify/"
                )

    # ========================================================
    # 【保留】
    # CheckMacValue 驗證
    # ========================================================

    # 【新增】公開給 Service 使用（Service 不直接碰 MAC 計算）
    def verify_check_mac_value(
        self,
        request_data,
    ):
        return self._verify_check_mac_value(
            request_data
        )

    def _verify_check_mac_value(
        self,
        request_data,
    ):
        """
        驗證：

            ECPay Mock
                ↓
            Bank Mock

        的 CheckMacValue。

        ========================================================
        責任
        ========================================================

        Adapter 負責：

            request_data
                ↓
            移除 CheckMacValue
                ↓
            HashKey / HashIV
                ↓
            重新計算
                ↓
            比對 received MAC
        """

        # ----------------------------------------------------
        # 【保留】
        #
        # Service 直接單元測試 Gateway 時，
        # 如果沒有 HTTP request_data，
        # 可以允許略過外部 Request MAC 驗證。
        #
        # 但正式 HTTP 流程：
        # request_data 一定會存在。
        # ----------------------------------------------------

        if request_data is None:

            logger.debug(
                "Bank Mock create_virtual_account "
                "未提供 request_data，"
                "略過外部 MAC 驗證"
            )

            return True

        # ----------------------------------------------------
        # 【保留】
        # request_data 必須是 dict
        # ----------------------------------------------------

        if not isinstance(
            request_data,
            dict,
        ):

            logger.warning(
                "Bank Mock request_data 格式錯誤：不是 dict"
            )

            raise ValueError(
                "request_data 必須是 dict"
            )

        # ----------------------------------------------------
        # 【保留】
        # CheckMacValue 必須存在
        # ----------------------------------------------------

        if "CheckMacValue" not in request_data:

            logger.warning(
                "Bank Mock 收到請求但缺少 CheckMacValue"
            )

            raise ValueError(
                "缺少 CheckMacValue"
            )

        received_mac = request_data.get(
            "CheckMacValue"
        )

        if not received_mac:

            logger.warning(
                "Bank Mock 收到空的 CheckMacValue"
            )

            raise ValueError(
                "CheckMacValue 不可為空"
            )

        # ----------------------------------------------------
        # 【保留】
        # 不修改原始 request_data
        # ----------------------------------------------------

        payload = dict(
            request_data
        )

        payload.pop(
            "CheckMacValue",
            None,
        )

        # ----------------------------------------------------
        # 【保留】
        # HashKey / HashIV
        # ----------------------------------------------------

        hash_key = getattr(
            settings,
            "ECPAY_HASH_KEY",
            "",
        )

        hash_iv = getattr(
            settings,
            "ECPAY_HASH_IV",
            "",
        )

        if not hash_key:

            logger.error(
                "Bank Mock 未設定 ECPAY_HASH_KEY"
            )

            raise RuntimeError(
                "未設定 ECPAY_HASH_KEY"
            )

        if not hash_iv:

            logger.error(
                "Bank Mock 未設定 ECPAY_HASH_IV"
            )

            raise RuntimeError(
                "未設定 ECPAY_HASH_IV"
            )

        # ----------------------------------------------------
        # 【保留】
        # 重新計算 MAC
        # ----------------------------------------------------

        try:

            expected_mac = (
                generate_check_mac_value(
                    payload,
                    hash_key,
                    hash_iv,
                )
            )

        except Exception as ex:

            logger.exception(
                "Bank Mock CheckMacValue 計算失敗"
            )

            raise RuntimeError(
                "CheckMacValue 計算失敗"
            ) from ex

        # ----------------------------------------------------
        # 【本次修改】
        #
        # 使用 compare_digest 進行 MAC 比對。
        # ----------------------------------------------------

        if not hmac.compare_digest(
            str(received_mac).upper(),
            str(expected_mac).upper(),
        ):

            logger.warning(
                "Bank Mock CheckMacValue 驗證失敗"
            )

            raise ValueError(
                "CheckMacValue 驗證失敗"
            )

        logger.debug(
            "Bank Mock CheckMacValue 驗證成功"
        )

        return True

    # ========================================================
    # 產生虛擬帳號
    # ========================================================

    def _generate_virtual_account(self):
        """
        Bank Mock 自己產生 ATM 虛擬帳號。

        Bank Mock 負責：

            bank_code
            v_account
        """

        random_number = random.randint(
            100000000000,
            999999999999,
        )

        return (
            f"{self.bank_code}"
            f"{random_number}"
        )

    # ========================================================
    # 產生 ATM 到期時間
    # ========================================================

    def _generate_expire_date(self):

        return (
            timezone.now()
            + timedelta(
                days=self.expire_days
            )
        )

    # ========================================================
    # 【本次修改】
    # 建立 ATM 虛擬帳號
    # ========================================================

    def create_virtual_account(
        self,
        merchant_trade_no: str,
        trade_amt: Decimal,
        request_data=None,
    ) -> dict:
        """
        Bank Mock 建立 ATM 虛擬帳號。

        ========================================================
        流程
        ========================================================

        1. 驗證 merchant_trade_no
        2. 驗證 trade_amt
        3. 驗證 CheckMacValue
        4. 查詢既有 merchant_trade_no
        5. 驗證重複交易金額
        6. Bank Mock 產生 ATM 資訊
        7. ORM 寫入 VirtualAccount
        8. collision retry
        9. 回傳 ATM 資訊

        ========================================================
        最重要的安全邊界
        ========================================================

        _verify_check_mac_value()

        必須發生在：

            VirtualAccount.objects.create()

        之前。
        """

        # ====================================================
        # 基本驗證
        # ====================================================

        if not merchant_trade_no:

            logger.warning(
                "Bank Mock 建立 ATM 時缺少 merchant_trade_no"
            )

            raise ValueError(
                "merchant_trade_no 不可為空"
            )

        if trade_amt is None:

            logger.warning(
                "Bank Mock 建立 ATM 時缺少 trade_amt"
            )

            raise ValueError(
                "trade_amt 不可為空"
            )

        # ----------------------------------------------------
        # 【保留】
        # Decimal 正規化
        # ----------------------------------------------------

        try:

            trade_amt = Decimal(
                str(trade_amt)
            )

        except Exception as ex:

            logger.warning(
                "Bank Mock trade_amt 格式錯誤：%s",
                ex,
            )

            raise ValueError(
                f"trade_amt 格式錯誤: {ex}"
            ) from ex

        if trade_amt <= 0:

            logger.warning(
                "Bank Mock trade_amt 必須大於 0：trade_amt=%s",
                trade_amt,
            )

            raise ValueError(
                "trade_amt 必須大於 0"
            )

        # ====================================================
        # 【保留】
        #
        # CheckMacValue 驗證必須在 ORM 前。
        # ====================================================

        self._verify_check_mac_value(
            request_data
        )

        # ====================================================
        # 【保留】
        #
        # 查詢 merchant_trade_no 是否已存在。
        # ====================================================

        try:

            existing_account = (
                VirtualAccount.objects
                .filter(
                    merchant_trade_no=merchant_trade_no
                )
                .first()
            )

        except Exception as ex:

            logger.exception(
                "Bank Mock 查詢既有 VirtualAccount 失敗"
            )

            raise RuntimeError(
                "查詢 Bank Mock ATM 帳號失敗"
            ) from ex

        # ====================================================
        # 【保留】
        # 相同 merchant_trade_no
        # ====================================================

        if existing_account:

            if (
                existing_account.trade_amt
                != trade_amt
            ):

                logger.warning(
                    "Bank Mock 發現相同 merchant_trade_no "
                    "但 trade_amt 不一致："
                    "merchant_trade_no=%s "
                    "existing_trade_amt=%s "
                    "request_trade_amt=%s",
                    merchant_trade_no,
                    existing_account.trade_amt,
                    trade_amt,
                )

                raise ValueError(
                    "相同 merchant_trade_no 的付款金額不一致"
                )

            logger.info(
                "Bank Mock 重用既有 ATM："
                "merchant_trade_no=%s",
                merchant_trade_no,
            )

            return self.build_account_response(
                existing_account
            )

        # ====================================================
        # Bank Mock 自己產生 ATM 資訊
        # ====================================================

        bank_code = self.bank_code

        expire_date = (
            self._generate_expire_date()
        )

        virtual_account = None

        # ====================================================
        # 【保留】
        # 最多嘗試 5 次
        # ====================================================

        for attempt in range(1, 6):

            v_account = (
                self._generate_virtual_account()
            )

            try:

                with transaction.atomic():

                    virtual_account = (
                        VirtualAccount.objects.create(
                            merchant_trade_no=(
                                merchant_trade_no
                            ),
                            bank_code=bank_code,
                            v_account=v_account,
                            trade_amt=trade_amt,
                            expire_date=expire_date,
                            status="atm_created",
                        )
                    )

                logger.info(
                    "Bank Mock ATM 建立成功："
                    "merchant_trade_no=%s attempt=%s",
                    merchant_trade_no,
                    attempt,
                )

                break

            except IntegrityError as ex:

                # ------------------------------------------------
                # 【保留】
                #
                # 先確認是不是另一個 request
                # 已經建立相同 merchant_trade_no。
                # ------------------------------------------------

                try:

                    existing_account = (
                        VirtualAccount.objects
                        .filter(
                            merchant_trade_no=(
                                merchant_trade_no
                            )
                        )
                        .first()
                    )

                except Exception as query_ex:

                    logger.exception(
                        "Bank Mock IntegrityError 後，"
                        "重新查詢 merchant_trade_no 失敗"
                    )

                    raise RuntimeError(
                        "檢查 Bank Mock ATM 重複資料失敗"
                    ) from query_ex

                if existing_account:

                    if (
                        existing_account.trade_amt
                        != trade_amt
                    ):

                        raise ValueError(
                            "相同 merchant_trade_no "
                            "的付款金額不一致"
                        )

                    logger.info(
                        "Bank Mock concurrent request "
                        "已建立 ATM，直接重用："
                        "merchant_trade_no=%s",
                        merchant_trade_no,
                    )

                    virtual_account = (
                        existing_account
                    )

                    break

                # ------------------------------------------------
                # 【保留】
                #
                # merchant_trade_no 不存在，
                # 才視為可能是 v_account collision。
                # ------------------------------------------------

                logger.warning(
                    "Bank Mock ATM 建立 IntegrityError，"
                    "可能是 v_account collision："
                    "merchant_trade_no=%s "
                    "attempt=%s error=%s",
                    merchant_trade_no,
                    attempt,
                    ex,
                )

                continue

            except Exception as ex:

                logger.exception(
                    "Bank Mock 建立 VirtualAccount 失敗："
                    "merchant_trade_no=%s",
                    merchant_trade_no,
                )

                raise RuntimeError(
                    "建立 Bank Mock ATM 帳號失敗"
                ) from ex

        # ====================================================
        # 【保留】
        # 5 次都失敗
        # ====================================================

        if virtual_account is None:

            logger.error(
                "Bank Mock 無法產生唯一 ATM 虛擬帳號："
                "merchant_trade_no=%s",
                merchant_trade_no,
            )

            raise RuntimeError(
                "無法產生唯一的 ATM 虛擬帳號"
            )

        return self.build_account_response(
            virtual_account
        )

    # ========================================================
    # 【本次修改】
    # 統一建立 ATM Response
    # ========================================================

    def build_account_response(
        self,
        account,
    ) -> dict:
        """
        【本次修改】

        實作 BankAccountGateway 的 abstract method。

        將 VirtualAccount Model
        轉成 Service / HTTP 可以使用的 dict。
        """

        if account is None:

            raise ValueError(
                "VirtualAccount 不可為空"
            )

        trade_amt = str(
            int(account.trade_amt)
        )

        return {
            "status": True,

            "merchant_trade_no": (
                account.merchant_trade_no
            ),

            "bank_code": (
                account.bank_code
            ),

            "v_account": (
                account.v_account
            ),

            "trade_amt": trade_amt,

            "expire_date": (
                account.expire_date.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            ),

            "payment_status": (
                account.status
            ),
        }

    # ========================================================
    # 【保留】
    # 取得 VirtualAccount
    # ========================================================

    def get_virtual_account(
        self,
        merchant_trade_no: str,
    ):

        if not merchant_trade_no:

            logger.warning(
                "Bank Mock 查詢 ATM 時缺少 merchant_trade_no"
            )

            raise ValueError(
                "merchant_trade_no 不可為空"
            )

        try:

            return VirtualAccount.objects.get(
                merchant_trade_no=merchant_trade_no
            )

        except VirtualAccount.DoesNotExist:

            logger.info(
                "Bank Mock 找不到 VirtualAccount："
                "merchant_trade_no=%s",
                merchant_trade_no,
            )

            return None

        except Exception as ex:

            logger.exception(
                "Bank Mock 取得 VirtualAccount 失敗："
                "merchant_trade_no=%s",
                merchant_trade_no,
            )

            raise RuntimeError(
                "取得 Bank Mock ATM 帳號失敗"
            ) from ex

    # ========================================================
    # 【保留】
    # 更新 ATM 狀態
    # ========================================================

    def update_account_status(
        self,
        account,
        status: str,
    ):

        allowed_statuses = {
            "atm_created",
            "unpaid",
            "paid",
            "expired",
        }

        if status not in allowed_statuses:

            logger.warning(
                "Bank Mock 收到不允許的 ATM status：%s",
                status,
            )

            raise ValueError(
                f"不允許的 ATM status: {status}"
            )

        try:

            account.status = status

            account.save(
                update_fields=[
                    "status"
                ]
            )

            logger.info(
                "Bank Mock ATM 狀態更新成功："
                "merchant_trade_no=%s status=%s",
                account.merchant_trade_no,
                status,
            )

            return account

        except Exception as ex:

            logger.exception(
                "Bank Mock 更新 ATM 狀態失敗："
                "merchant_trade_no=%s status=%s",
                getattr(
                    account,
                    "merchant_trade_no",
                    None,
                ),
                status,
            )

            raise RuntimeError(
                "更新 Bank Mock ATM 狀態失敗"
            ) from ex

    # ========================================================
    # Bank Mock → ECPay Mock
    # ========================================================

    def notify_ecpay_mock(
        self,
        account,
        payment_status: str,
    ) -> dict:
        """
        使用 HTTPX 將 Bank Mock
        的付款結果 callback 給 ECPay Mock。

        HTTPX 只存在 Adapter。
        """

        if not self.ecpay_mock_url:

            logger.error(
                "Bank Mock 未設定 ECPay Mock callback URL"
            )

            raise RuntimeError(
                "未設定 ECPAY_MOCK_PAYMENT_NOTIFY_URL"
            )

        payload = {
            "merchant_trade_no": (
                account.merchant_trade_no
            ),

            "trade_amt": str(
                int(account.trade_amt)
            ),

            "bank_code": (
                account.bank_code
            ),

            "v_account": (
                account.v_account
            ),

            "expire_date": (
                account.expire_date.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            ),

            # ------------------------------------------------
            # 【保留】
            #
            # Bank Mock → ECPay Mock
            # 的付款狀態。
            # ------------------------------------------------

            "status": payment_status,

            # 【新增】標記「來自 ATM 模擬頁」的通知（已簽進 CheckMacValue）
            # 商城只對帶 simulate="1" 的通知，放行逾期訂單改狀態；
            # 其他來源的 ATM 通知，逾期訂單仍然不可更改
            "simulate": "1",
        }

        # ====================================================
        # 【保留】
        # 產生 callback MAC
        # ====================================================

        try:

            payload[
                "CheckMacValue"
            ] = generate_check_mac_value(
                payload,
                settings.ECPAY_HASH_KEY,
                settings.ECPAY_HASH_IV,
            )

        except Exception as ex:

            logger.exception(
                "Bank Mock callback CheckMacValue 產生失敗："
                "merchant_trade_no=%s",
                account.merchant_trade_no,
            )

            raise RuntimeError(
                "產生 ECPay Mock callback MAC 失敗"
            ) from ex

        # ====================================================
        # 【保留】
        # HTTPX Backend-to-Backend
        # ====================================================

        try:
            logger.info("self.ecpay_mock_url=%s", self.ecpay_mock_url)

            response = httpx.post(
                self.ecpay_mock_url,
                json=payload,
                timeout=10.0,
            )

        except httpx.TimeoutException as ex:

            logger.exception(
                "Bank Mock → ECPay Mock timeout："
                "merchant_trade_no=%s",
                account.merchant_trade_no,
            )

            return {
                "status": False,
                "message": (
                    "ECPay Mock callback timeout"
                ),
                "error_type": (
                    type(ex).__name__
                ),
            }

        except httpx.RequestError as ex:

            logger.exception(
                "Bank Mock → ECPay Mock HTTP request error："
                "merchant_trade_no=%s",
                account.merchant_trade_no,
            )

            return {
                "status": False,
                "message": str(ex),
                "error_type": (
                    type(ex).__name__
                ),
            }

        except Exception as ex:

            logger.exception(
                "Bank Mock → ECPay Mock 發生未知錯誤："
                "merchant_trade_no=%s",
                account.merchant_trade_no,
            )

            return {
                "status": False,
                "message": str(ex),
                "error_type": (
                    type(ex).__name__
                ),
            }

        # ====================================================
        # 【保留】
        # HTTP Status
        # ====================================================

        if response.status_code != 200:

            logger.error(
                "ECPay Mock callback HTTP 失敗："
                "merchant_trade_no=%s "
                "status_code=%s response=%s",
                account.merchant_trade_no,
                response.status_code,
                response.text,
            )

            return {
                "status": False,
                "message": (
                    "ECPay Mock callback 失敗"
                ),
                "status_code": (
                    response.status_code
                ),
                "response": response.text,
            }

        # ====================================================
        # 【保留】
        # HTTP 200 仍要確認 JSON
        # ====================================================

        try:

            response_data = (
                response.json()
            )

        except ValueError:

            logger.error(
                "ECPay Mock callback HTTP 200，"
                "但回傳不是合法 JSON："
                "merchant_trade_no=%s response=%s",
                account.merchant_trade_no,
                response.text,
            )

            return {
                "status": False,
                "message": (
                    "ECPay Mock 回傳格式錯誤"
                ),
                "response": response.text,
            }

        if not isinstance(
            response_data,
            dict,
        ):

            logger.error(
                "ECPay Mock callback HTTP 200，"
                "但 JSON 不是 Object："
                "merchant_trade_no=%s response=%s",
                account.merchant_trade_no,
                response_data,
            )

            return {
                "status": False,
                "message": (
                    "ECPay Mock callback "
                    "回傳格式錯誤"
                ),
                "response": response_data,
            }

        # ====================================================
        # 【保留】
        # Business status
        # ====================================================

        gateway_status = (
            response_data.get(
                "status"
            )
        )

        if gateway_status is None:

            gateway_status = (
                response_data.get(
                    "success"
                )
            )

        is_business_success = (
            gateway_status is True
            or str(
                gateway_status
            ).strip().lower()
            in {
                "true",
                "success",
                "ok",
                "1",
            }
        )

        if not is_business_success:

            logger.warning(
                "ECPay Mock callback HTTP 200，"
                "但 business status 失敗："
                "merchant_trade_no=%s "
                "gateway_status=%s response=%s",
                account.merchant_trade_no,
                gateway_status,
                response_data,
            )

            return {
                "status": False,
                "message": (
                    "ECPay Mock callback "
                    "business status 失敗"
                ),
                "gateway_response": response_data,
            }

        logger.info(
            "Bank Mock → ECPay Mock callback 成功："
            "merchant_trade_no=%s payment_status=%s",
            account.merchant_trade_no,
            payment_status,
        )

        return {
            "status": True,
            "gateway_response": response_data,
        }