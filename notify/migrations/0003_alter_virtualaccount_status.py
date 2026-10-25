# 【新增】VirtualAccount.status 新增 cancelled 選項（僅 choices 變更，無 SQL 欄位變動）

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notify", "0002_alter_virtualaccount_bank_code_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="virtualaccount",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("cod_created", "COD_Created"),
                    ("atm_created", "ATM Created"),
                    ("unpaid", "Unpaid"),
                    ("paid", "Paid"),
                    ("expired", "Expired"),
                    ("cancelled", "Cancelled"),
                ],
                default="atm_created",
                max_length=20,
            ),
        ),
    ]
