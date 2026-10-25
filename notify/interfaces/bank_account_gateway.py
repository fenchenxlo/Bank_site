# ============================================================
# Bank Mock
# notify/interfaces/bank_account_gateway.py
# ============================================================

from abc import ABC, abstractmethod
from decimal import Decimal


class BankAccountGateway(ABC):
    """
    【本次修改】

    Bank Mock ATM Gateway Interface。

    ============================================================
    Gateway 的責任
    ============================================================

    1. 定義 Bank Mock Service 可以使用的能力
    2. 隔離 Service 與實際 Adapter 實作
    3. Service 不直接依賴 Django ORM
    4. Service 不直接處理 HTTPX
    5. Service 不直接處理 CheckMacValue

    ============================================================
    實際架構
    ============================================================

        View
          ↓
        BankAccountService
          ↓
        BankAccountGateway
          ↓
        BankAccountAdapter
          ↓
        ORM / HTTPX / CheckMacValue

    ============================================================
    CheckMacValue 特別注意
    ============================================================

    ECPay Mock → Bank Mock：

        request
          ↓
        BankAccountService
          ↓
        BankAccountGateway
          ↓
        BankAccountAdapter
          ↓
        驗證 CheckMacValue
          ↓
        VirtualAccount.objects.create()

    Service 不需要直接呼叫：

        verify_check_mac_value()

    因為：

        create_virtual_account()

    本身就是「真正建立 VirtualAccount 前的 Adapter 邊界」。

    因此 CheckMacValue 驗證作為 Adapter 內部責任，
    不列為 Service 必須直接呼叫的 abstract method。
    """

    # ========================================================
    # 建立 ATM 虛擬帳號
    # ========================================================

    @abstractmethod
    def create_virtual_account(
        self,
        merchant_trade_no: str,
        trade_amt: Decimal,
        request_data: dict,
    ) -> dict:
        """
        【本次修改】

        建立 ATM 虛擬帳號。

        Bank Mock 必須產生：

            1. bank_code
            2. v_account
            3. expire_date

        並寫入 Bank Mock 的 VirtualAccount DB。

        ========================================================
        request_data
        ========================================================

        request_data 必須保留。

        原因：

            ECPay Mock
                ↓
            CheckMacValue
                ↓
            Bank Mock View
                ↓
            BankAccountService
                ↓
            BankAccountGateway
                ↓
            BankAccountAdapter
                ↓
            驗證 CheckMacValue
                ↓
            ORM create

        注意：

        Interface 只負責把這項能力定義出來。

        真正的 CheckMacValue 驗證，
        仍由 BankAccountAdapter 負責。
        """

        raise NotImplementedError

    # ========================================================
    # 查詢 ATM 虛擬帳號
    # ========================================================

    @abstractmethod
    def get_virtual_account(
        self,
        merchant_trade_no: str,
    ):
        """
        【保留】

        查詢 ATM 虛擬帳號。

        回傳：

            VirtualAccount instance

        或：

            None
        """

        raise NotImplementedError

    # ========================================================
    # 更新 ATM 帳號狀態
    # ========================================================

    @abstractmethod
    def update_account_status(
        self,
        account,
        status: str,
    ):
        """
        【保留】

        更新 ATM 帳號狀態。

        目前支援：

            atm_created
            unpaid
            paid
            expired
        """

        raise NotImplementedError

    # ========================================================
    # 通知 ECPay Mock
    # ========================================================

    # 【新增】驗證上游（ECPay Mock）送來的 CheckMacValue
    @abstractmethod
    def verify_check_mac_value(
        self,
        request_data,
    ):
        pass

    @abstractmethod
    def notify_ecpay_mock(
        self,
        account,
        payment_status: str,
    ) -> dict:
        """
        【保留】

        將 Bank Mock 的付款結果通知 ECPay Mock。

        HTTPX 實際呼叫由 Adapter 負責。

        Service 不直接使用 httpx。
        """

        raise NotImplementedError

    # ========================================================
    # 將 VirtualAccount 轉成 Response Dict
    # ========================================================

    @abstractmethod
    def build_account_response(
        self,
        account,
    ) -> dict:
        """
        【修改】

        將 VirtualAccount 轉成 JSON / Service 可使用的 dict。

        實際資料組裝由 Adapter 負責。

        Service 不直接處理 Django Model 欄位組裝。
        """

        raise NotImplementedError