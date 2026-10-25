# ============================================================
# Bank_Mock
# notify/services/bank_account_service.py
# ============================================================

import logging
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from ..models import VirtualAccount

logger = logging.getLogger(__name__)


class BankAccountService:
    """
    Bank Mock ATM 業務 Service。

    Service 負責：

        1. ATM 建立流程
        2. ATM 查詢流程
        3. ATM 付款成功流程
        4. ATM 付款失敗流程

    Service 不負責：

        ❌ httpx.post()
        ❌ CheckMacValue 計算
        ❌ CheckMacValue 驗證

    實際架構：

        View
          ↓
        BankAccountService
          ↓
        BankAccountGateway Interface
          ↓
        BankAccountAdapter
          ↓
        ORM / HTTPX
    """

    # ========================================================
    # 初始化
    # ========================================================

    def __init__(
        self,
        gateway,
    ):
        """
        Dependency Injection。

        【保留】

        Service 不自己建立 Adapter，
        而是由外部注入 Gateway。

        這樣測試時可以替換 Gateway。
        """

        if gateway is None:
            raise ValueError(
                "BankAccountService 必須提供 gateway"
            )

        self.gateway = gateway

    # ========================================================
    # 建立 ATM 虛擬帳號
    # ========================================================

    def create_account(
        self,
        merchant_trade_no: str,
        trade_amt,
        request_data: dict,
    ) -> dict:
        """
        建立 ATM 虛擬帳號。

        流程：

            View
              ↓
            Service
              ↓
            Gateway
              ↓
            BankAccountAdapter
              ↓
            VirtualAccount

        【修改】

        request_data 必須一路傳到 Gateway。

        原本如果只傳：

            merchant_trade_no
            trade_amt

        那麼 Adapter 收不到：

            CheckMacValue

        導致：

            ECPay Mock
                ↓
            Bank Mock Adapter

        的 MAC 驗證無法真正執行。

        現在改成：

            request_data=request_data

        讓 BankAccountAdapter 可以在建立
        VirtualAccount 之前驗證 CheckMacValue。
        """

        # ====================================================
        # 【保留】
        # 基本驗證
        # ====================================================

        if not merchant_trade_no:
            raise ValueError(
                "merchant_trade_no 不可為空"
            )

        if trade_amt is None:
            raise ValueError(
                "trade_amt 不可為空"
            )

        # ====================================================
        # 【修改】
        # 呼叫 Gateway
        #
        # 重要：
        #
        # request_data 必須傳下去。
        #
        # 真正的 HTTP API 流程：
        #
        # ECPay Mock Adapter
        #       ↓
        # HTTPX
        #       ↓
        # Bank Mock View
        #       ↓
        # BankAccountService
        #       ↓
        # BankAccountAdapter
        #       ↓
        # 驗證 CheckMacValue
        #
        # ====================================================
        # 【修改】
        # BankAccountService 直接使用 Django ORM
        # 不再透過 self.gateway 建立 VirtualAccount。
        
        try:
            logger.info(
                "request_data：%s",
                request_data
            )

            bank_code = request_data.get(
                "bank_code"
            )

            v_account = request_data.get(
                "v_account"
            )

            expire_date = request_data.get(
                "expire_date"
            )
            
            status = request_data.get(
                "status"
            )

            if not bank_code:
                raise ValueError(
                    "bank_code 不可為空"
                )

            if not v_account:
                raise ValueError(
                    "v_account 不可為空"
                )

            if not expire_date:
                raise ValueError(
                    "expire_date 不可為空"
                )

            # 【新增】
            # 將 expire_date 轉成 Django DateTimeField
            # 可使用的 datetime。
            expire_datetime = parse_datetime(
                str(expire_date)
            )

            if expire_datetime is None:
                raise ValueError(
                    "expire_date 格式錯誤"
                )

            if timezone.is_naive(
                expire_datetime
            ):
                expire_datetime = timezone.make_aware(
                    expire_datetime
                )

            # 【修改】
            # Django ORM 建立或取得銀行端虛擬帳號。
            #
            # merchant_trade_no 是 unique 欄位，
            # 所以相同交易編號再次送達時，
            # 直接取得既有資料，不重複建立。
            virtual_account, created = (
                VirtualAccount.objects.get_or_create(
                    merchant_trade_no=merchant_trade_no,
                    defaults={
                        "bank_code": bank_code,
                        "v_account": v_account,
                        "trade_amt": trade_amt,
                        "expire_date": expire_datetime,
                        "status": "atm_created",
                    },
                )
            )

            logger.info(
                "VirtualAccount %s：merchant_trade_no=%s",
                "建立成功" if created else "已存在，直接取得",
                virtual_account.merchant_trade_no,
            )

            # 【新增】
            # 維持原本 Service 對外回傳 dict 的形式。
            result = {
                "success": True,
                "status": "created"
                if created
                else "existing",
                "message": (
                    "ATM 虛擬帳號建立成功"
                    if created
                    else "ATM 虛擬帳號已存在"
                ),
                "merchant_trade_no": (
                    virtual_account.merchant_trade_no
                ),
                "bank_code": (
                    virtual_account.bank_code
                ),
                "v_account": (
                    virtual_account.v_account
                ),
                "trade_amt": str(
                    virtual_account.trade_amt
                ),
                "expire_date": (
                    virtual_account.expire_date.isoformat()
                    if virtual_account.expire_date
                    else None
                ),
                "payment_status": (
                    virtual_account.status
                ),
            }

        except ValueError:
            raise

        except Exception as ex:

            logger.exception(
                "Bank Mock 建立 ATM 虛擬帳號失敗"
            )

            raise RuntimeError(
                "Bank Mock 建立 ATM 虛擬帳號失敗"
            ) from ex

        # ====================================================
        # 【保留】
        # 驗證 Gateway 回傳結果
        # ====================================================

        if not result:
            raise RuntimeError(
                "Bank Mock 沒有回傳 ATM 資訊"
            )

        return result

    # ========================================================
    # 查詢 ATM 虛擬帳號
    # ========================================================

    def get_account(
        self,
        merchant_trade_no: str,
    ):
        """
        查詢 ATM 虛擬帳號。

        Service 直接操作 ORM。
        """

        if not merchant_trade_no:

            raise ValueError(
                "merchant_trade_no 不可為空"
            )

        try:

            account = (
                VirtualAccount.objects
                .get(
                    merchant_trade_no=merchant_trade_no
                )
            )

        except VirtualAccount.DoesNotExist as ex:

            raise LookupError(
                "找不到 ATM 虛擬帳號"
            ) from ex

        except Exception as ex:

            logger.exception(
                "Bank Mock 查詢 ATM 帳號失敗"
            )

            raise RuntimeError(
                "Bank Mock 查詢 ATM 帳號失敗"
            ) from ex

        return account

    # ========================================================
    # 模擬 ATM 付款成功
    # ========================================================

    def simulate_paid(
        self,
        merchant_trade_no: str,
    ) -> dict:
        """
        模擬 ATM 付款成功。

        【修改】流程對調：

            先通知 ECPay Mock（含商店更新）
              ↓ 成功才
            寫 Bank DB status = paid
        """

        account = self.get_account(
            merchant_trade_no
        )

        # 【新增】已取消的帳號不可再模擬付款
        if account.status == "cancelled":
            raise ValueError(
                "此 ATM 帳號已取消，無法模擬付款"
            )

        # ====================================================
        # 【保留】
        # 防止重複付款
        # ====================================================

        if account.status == "paid":

            raise ValueError(
                "此 ATM 帳號已經付款完成"
            )

        # ====================================================
        # 【搬移】Bank → ECPay Mock 通知，從「寫 DB 之後」移到「之前」
        # payload 只讀 account，不需要先改狀態
        # ====================================================

        try:

            result = (
                self.gateway.notify_ecpay_mock(
                    account=account,
                    payment_status="paid",
                )
            )

        except Exception as ex:

            logger.exception(
                "Bank Mock → ECPay Mock "
                "付款成功 callback 失敗"
            )

            raise RuntimeError(
                "通知 ECPay Mock 付款成功失敗"
            ) from ex

        # ====================================================
        # 【新增】
        # adapter 失敗時回 {"status": False}，不會丟例外，
        # 這裡要主動檢查：失敗就不寫 Bank DB，並帶出原因
        # ====================================================

        if not result.get("status"):

            raise RuntimeError(
                "ECPay Mock 處理失敗，Bank 未更新："
                f"{result.get('response') or result.get('message')}"
            )

        # ====================================================
        # 【搬移】
        # 原本在通知之前的 transaction.atomic() 區塊，
        # 內容原封不動，搬到下游成功之後。
        # ====================================================

        try:

            with transaction.atomic():

                account = (
                    VirtualAccount.objects
                    .select_for_update()
                    .get(
                        merchant_trade_no=merchant_trade_no
                    )
                )

                if account.status == "paid":

                    raise ValueError(
                        "此 ATM 帳號已經付款完成"
                    )

                account.status = "paid"

                account.save(
                    update_fields=["status"]
                )

        except ValueError:
            raise

        except VirtualAccount.DoesNotExist as ex:

            logger.exception(
                "找不到 Bank Mock ATM 帳號：merchant_trade_no=%s",
                merchant_trade_no,
            )

            raise LookupError(
                "找不到 ATM 虛擬帳號"
            ) from ex

        except Exception as ex:

            logger.exception(
                "Bank Mock 更新 ATM 付款狀態失敗"
            )

            raise RuntimeError(
                "Bank Mock 更新 ATM 付款狀態失敗"
            ) from ex

        return result

    # def simulate_paid(
        # self,
        # merchant_trade_no: str,
    # ) -> dict:
        # """
        # 模擬 ATM 付款成功。

        # 流程：

            # View
              # ↓
            # Service
              # ↓
            # Gateway
              # ↓
            # Adapter
              # ↓
            # 更新 Bank DB
              # ↓
            # HTTPX
              # ↓
            # ECPay Mock
        # """

        # account = self.get_account(
            # merchant_trade_no
        # )

        # # ====================================================
        # # 【保留】
        # # 防止重複付款
        # # ====================================================

        # if account.status == "paid":

            # raise ValueError(
                # "此 ATM 帳號已經付款完成"
            # )

        # # ====================================================
        # # 【修改】
        # # 更新 Bank Mock 狀態
        # #
        # # Service 直接操作 ORM。
        # #
        # # 使用：
        # #     transaction.atomic()
        # #     select_for_update()
        # #
        # # 以 merchant_trade_no 鎖定同一筆 ATM 帳號，
        # # 避免多個連線同時進行付款造成競態條件。
        # # ====================================================

        # try:

            # with transaction.atomic():

                # account = (
                    # VirtualAccount.objects
                    # .select_for_update()
                    # .get(
                        # merchant_trade_no=merchant_trade_no
                    # )
                # )

                # # ------------------------------------------------
                # # 【修改】
                # # 鎖定後再次確認付款狀態。
                # #
                # # 前面的 account.status == "paid"
                # # 只能做一般性檢查；
                # # 真正的競態防護要以鎖定後的資料為準。
                # # ------------------------------------------------

                # if account.status == "paid":

                    # raise ValueError(
                        # "此 ATM 帳號已經付款完成"
                    # )

                # account.status = "paid"

                # account.save(
                    # update_fields=["status"]
                # )

        # except ValueError:
            # raise

        # except VirtualAccount.DoesNotExist as ex:

            # logger.exception(
                # "找不到 Bank Mock ATM 帳號：merchant_trade_no=%s",
                # merchant_trade_no,
            # )

            # raise LookupError(
                # "找不到 ATM 虛擬帳號"
            # ) from ex

        # except Exception as ex:

            # logger.exception(
                # "Bank Mock 更新 ATM 付款狀態失敗"
            # )

            # raise RuntimeError(
                # "Bank Mock 更新 ATM 付款狀態失敗"
            # ) from ex

        # # ====================================================
        # # 【保留】
        # # Bank Mock → ECPay Mock
        # #
        # # CheckMacValue 的產生責任：
        # #
        # # BankAccountAdapter
        # #
        # # Service 不處理 MAC。
        # # ====================================================

        # try:

            # result = (
                # self.gateway.notify_ecpay_mock(
                    # account=account,
                    # payment_status="paid",
                # )
            # )

        # except Exception as ex:

            # logger.exception(
                # "Bank Mock → ECPay Mock "
                # "付款成功 callback 失敗"
            # )

            # raise RuntimeError(
                # "通知 ECPay Mock 付款成功失敗"
            # ) from ex

        # return result

    # ========================================================
    # 模擬 ATM 付款失敗
    # ========================================================

    def simulate_failed(
        self,
        merchant_trade_no: str,
    ) -> dict:
        """
        模擬 ATM 付款失敗。

        【修改】流程對調：

            先通知 ECPay Mock（含商店更新）
              ↓ 成功才
            寫 Bank DB status = unpaid
        """

        account = self.get_account(
            merchant_trade_no
        )

        # 【新增】已取消的帳號不可再模擬付款失敗
        if account.status == "cancelled":
            raise ValueError(
                "此 ATM 帳號已取消，無法模擬付款失敗"
            )

        # ====================================================
        # 【刪除】
        # 已付款的 ATM 不可再次模擬失敗
        # （移除後，已付款的帳號也可以再按「模擬未收到款項」）
        # ====================================================

        # if account.status == "paid":
        #
        #     raise ValueError(
        #         "此 ATM 帳號已經付款完成，"
        #         "不可再模擬付款失敗"
        #     )

        # ====================================================
        # 【搬移】Bank → ECPay Mock 通知，移到寫 DB 之前
        # ====================================================

        try:

            result = (
                self.gateway.notify_ecpay_mock(
                    account=account,
                    payment_status="atm_failed",
                )
            )

        except Exception as ex:

            logger.exception(
                "Bank Mock → ECPay Mock "
                "付款失敗 callback 失敗"
            )

            raise RuntimeError(
                "通知 ECPay Mock 付款失敗失敗"
            ) from ex

        # ====================================================
        # 【新增】
        # 下游失敗就不寫 Bank DB，並帶出原因
        # ====================================================

        if not result.get("status"):

            raise RuntimeError(
                "ECPay Mock 處理失敗，Bank 未更新："
                f"{result.get('response') or result.get('message')}"
            )

        # ====================================================
        # 【搬移】
        # 原本在通知之前的 transaction.atomic() 區塊，
        # 內容原封不動，搬到下游成功之後。
        # 不改 models，failed 先存成 unpaid。
        # ====================================================

        try:

            with transaction.atomic():

                account = (
                    VirtualAccount.objects
                    .select_for_update()
                    .get(
                        merchant_trade_no=merchant_trade_no
                    )
                )

                account.status = "unpaid"

                account.save(
                    update_fields=["status"]
                )

        except VirtualAccount.DoesNotExist as ex:

            logger.exception(
                "找不到 Bank Mock ATM 帳號：merchant_trade_no=%s",
                merchant_trade_no,
            )

            raise LookupError(
                "找不到 ATM 虛擬帳號"
            ) from ex

        except Exception as ex:

            logger.exception(
                "Bank Mock 更新 ATM 付款失敗狀態失敗"
            )

            raise RuntimeError(
                "Bank Mock 更新 ATM 付款失敗狀態失敗"
            ) from ex

        return result

    # ========================================================
    # 【新增】模擬 ATM 逾期未付款
    #
    # 流程與 simulate_failed 相同（先通知下游、成功才寫 Bank DB）：
    #
    #   Bank  --atm_expired-->  ECPay Mock (PaymentRequest=atm_expired)
    #                              --expired-->  商城 (Payment/Order=expired，釋放庫存)
    #   三層都成功才把 VirtualAccount.status 寫成 expired
    #   （VirtualAccount.status 本來就有 expired 選項，不需 migration）
    # ========================================================
    # 【新增】取消 ATM 虛擬帳號（由 ECPay Mock 呼叫，Bank 不再回通知）
    def cancel_account(
        self,
        merchant_trade_no: str,
        request_data: dict,
    ) -> dict:

        # 【新增】驗證 ECPay Mock 送來的 CheckMacValue
        self.gateway.verify_check_mac_value(
            request_data
        )

        # 【新增】刪除訂單時帶 delete_record="1"（已簽進 CheckMacValue）：把已取消的虛擬帳號整筆刪除。
        # 找不到視為成功（沒東西可刪，可重複呼叫）；必須已是 cancelled，避免誤刪仍有效的帳號
        if str(request_data.get("delete_record", "")) == "1":
            account = VirtualAccount.objects.filter(
                merchant_trade_no=merchant_trade_no
            ).first()
            if account is not None:
                if account.status != "cancelled":
                    raise ValueError(
                        f"此 ATM 帳號狀態為 {account.status}，請先取消訂單再刪除"
                    )
                account.delete()
            return {
                "status": True,
                "merchant_trade_no": merchant_trade_no,
                "account_status": "deleted",
            }

        account = self.get_account(
            merchant_trade_no
        )

        # 【新增】已付款 / 已逾期的帳號不可取消
        if account.status in ("paid", "expired"):
            raise ValueError(
                f"此 ATM 帳號狀態為 {account.status}，無法取消"
            )

        # 【新增】Bank 是鏈路末端，無下游呼叫，直接寫 DB
        account.status = "cancelled"
        account.save(update_fields=["status"])

        return {
            "status": True,
            "merchant_trade_no": merchant_trade_no,
            "account_status": "cancelled",
        }

    def simulate_expired(
        self,
        merchant_trade_no: str,
    ) -> dict:

        account = self.get_account(
            merchant_trade_no
        )

        # 【新增】已逾期的帳號不重複送（商城端逾期為終態，重送只會被擋）
        if account.status == "expired":
            raise ValueError(
                "此 ATM 帳號已經逾期，不需重複模擬"
            )

        # 【新增】已取消的帳號不可再模擬逾期
        if account.status == "cancelled":
            raise ValueError(
                "此 ATM 帳號已取消，無法模擬逾期"
            )

        try:
            result = (
                self.gateway.notify_ecpay_mock(
                    account=account,
                    payment_status="atm_expired",   # 【重點】ECPay Mock 以此判斷為逾期
                )
            )
        except Exception as ex:
            logger.exception(
                "Bank Mock → ECPay Mock 逾期 callback 失敗"
            )
            raise RuntimeError(
                "通知 ECPay Mock 逾期未付款失敗"
            ) from ex

        # 【重點】下游失敗就不寫 Bank DB，避免三邊狀態不一致
        if not result.get("status"):
            raise RuntimeError(
                "ECPay Mock 處理失敗，Bank 未更新："
                f"{result.get('response') or result.get('message')}"
            )

        try:
            with transaction.atomic():
                account = (
                    VirtualAccount.objects
                    .select_for_update()
                    .get(merchant_trade_no=merchant_trade_no)
                )
                account.status = "expired"   # 【重點】Bank DB 寫入逾期
                account.save(update_fields=["status"])
        except VirtualAccount.DoesNotExist as ex:
            raise LookupError("找不到 ATM 虛擬帳號") from ex
        except Exception as ex:
            logger.exception("Bank Mock 更新 ATM 逾期狀態失敗")
            raise RuntimeError(
                "Bank Mock 更新 ATM 逾期狀態失敗"
            ) from ex

        return result

    # def simulate_failed(
        # self,
        # merchant_trade_no: str,
    # ) -> dict:
        # """
        # 模擬 ATM 付款失敗。

        # 注意：

        # VirtualAccount 目前沒有要求一定要
        # 將資料庫 status 改成 failed。

        # 所以這裡只：

            # 1. 找到 ATM
            # 2. 通知 ECPay Mock failed

        # 不自行操作 ORM。
        # """

        # account = self.get_account(
            # merchant_trade_no
        # )

        # # ====================================================
        # # 【刪除】
        # # 已付款的 ATM 不可再次模擬失敗
        # # （移除後，已付款的帳號也可以再按「模擬未收到款項」）
        # # ====================================================

        # # if account.status == "paid":
        # #
        # #     raise ValueError(
        # #         "此 ATM 帳號已經付款完成，"
        # #         "不可再模擬付款失敗"
        # #     )

        # # ====================================================
        # # 【修改】
        # # 更新 Bank Mock 狀態
        # #
        # # Service 直接操作 ORM。
        # #
        # # 模擬付款失敗時：
        # #
        # #     VirtualAccount.status = "unpaid"
        # # ====================================================

        # try:

            # with transaction.atomic():

                # account = (
                    # VirtualAccount.objects
                    # .select_for_update()
                    # .get(
                        # merchant_trade_no=merchant_trade_no
                    # )
                # )

                # account.status = "unpaid"

                # account.save(
                    # update_fields=["status"]
                # )

        # except VirtualAccount.DoesNotExist as ex:

            # logger.exception(
                # "找不到 Bank Mock ATM 帳號：merchant_trade_no=%s",
                # merchant_trade_no,
            # )

            # raise LookupError(
                # "找不到 ATM 虛擬帳號"
            # ) from ex

        # except Exception as ex:

            # logger.exception(
                # "Bank Mock 更新 ATM 付款失敗狀態失敗"
            # )

            # raise RuntimeError(
                # "Bank Mock 更新 ATM 付款失敗狀態失敗"
            # ) from ex

        # # ====================================================
        # # 【保留】
        # # Bank Mock → ECPay Mock
        # #
        # # 付款失敗 callback。
        # #
        # # Adapter 負責：
        # #
        # #     1. 建立 callback payload
        # #     2. 產生 CheckMacValue
        # #     3. HTTPX POST
        # # ====================================================

        # try:

            # result = (
                # self.gateway.notify_ecpay_mock(
                    # account=account,
                    # payment_status="atm_failed",
                # )
            # )

        # except Exception as ex:

            # logger.exception(
                # "Bank Mock → ECPay Mock "
                # "付款失敗 callback 失敗"
            # )

            # raise RuntimeError(
                # "通知 ECPay Mock 付款失敗失敗"
            # ) from ex

        # return result