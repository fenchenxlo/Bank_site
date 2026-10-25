from django.urls import path,include
from notify.views import (
    home,
    create_account,
    account_detail,
    simulate_paid,
    simulate_failed,
    simulate_expired,   # 【新增】模擬逾期未付款
    cancel_account,     # 【新增】取消 ATM 虛擬帳號（ECPay Mock 呼叫）
    db_query_tool,
    query_and_simulate,   # 新增:import 新的 view
#     ecpay_notify,
)

app_name = "notify"

urlpatterns = [
    path('', home, name='home'),
    path('create_account/', create_account, name='create_account'),
    path("account_detail/<str:merchant_trade_no>/",account_detail,name="account_detail"),
    path("simulate_paid/<str:merchant_trade_no>/",simulate_paid,name="simulate_paid"),
    path("simulate_failed/<str:merchant_trade_no>/",simulate_failed,name="simulate_failed"),
    path("simulate_expired/<str:merchant_trade_no>/",simulate_expired,name="simulate_expired"),  # 【新增】模擬逾期未付款
    path("cancel_account/<str:merchant_trade_no>/",cancel_account,name="cancel_account"),  # 【新增】取消 ATM 虛擬帳號
    path("admin-tools/db_query_tool/", db_query_tool, name="db_query_tool"),  # 新增
    path("admin-tools/query_and_simulate/", query_and_simulate, name="query_and_simulate"),  # 新增:查詢+模擬付款合併頁
#     path("notify/", ecpay_notify, name="ecpay_notify"),        # 綠界 server-to-server 回傳
]
