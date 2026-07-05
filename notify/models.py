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
        max_length=3
    )

    v_account = models.CharField(
        max_length=20,
        unique=True
    )

    trade_amt = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    expire_date = models.DateTimeField()

    status = models.CharField(
        max_length=20,
        choices=[
            ("atm_created", "Atm_Created"),
            ("unpaid", "UnPaid"),
            ("paid", "Paid"),
            ("expired", "Expired"),
        ],
        default="unpaid"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return self.merchant_trade_no