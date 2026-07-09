from django.contrib import admin
from .models import VirtualAccount
# Register your models here.

@admin.register(VirtualAccount)
class VirtualAccount(admin.ModelAdmin):
    list_display = ("merchant_trade_no", "bank_code", "v_account", "trade_amt", "expire_date", "status", "created_at")
    search_fields = ("merchant_trade_no", "status", "created_at")
    list_filter = ("status", "trade_amt", "created_at")
