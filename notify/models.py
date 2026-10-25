# bank/models.py

from django.db import models


class VirtualAccount(models.Model):
    """
    銀行端收到綠界通知後建立的虛擬帳號資料
    """

    merchant_trade_no = models.CharField(
        max_length=50,
        unique=True
    )

    bank_code = models.CharField(
        max_length=3,
        null=True,
        blank=True
    )

    v_account = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True
    )

    trade_amt = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    expire_date = models.DateTimeField(
        null=True,
        blank=True
    )

    # 【修改】
    # 建立 ATM 帳號時固定為 atm_created。
    # 尚未付款則為 unpaid。
    status = models.CharField(
        max_length=20,
        choices=[
		    ("pending", "Pending"),
		    ("cod_created", "COD_Created"),
            ("atm_created", "ATM Created"),
            ("unpaid", "Unpaid"),
            ("paid", "Paid"),
            ("expired", "Expired"),
            ("cancelled", "Cancelled"),   # 【新增】商城取消訂單，同步取消 ATM 虛擬帳號
        ],
        default="atm_created"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return self.merchant_trade_no