from django.urls import path,include
from notify.views import (
    home,
    create_account,
    account_detail,
    simulate_paid,
    simulate_failed,
#     ecpay_notify,
)

urlpatterns = [
    path('', home, name='home'),
    path('create_account/', create_account, name='create_account'),
    path("account_detail/<str:merchant_trade_no>/",account_detail,name="account_detail"),
    path("simulate_paid/<str:merchant_trade_no>/",simulate_paid,name="simulate_paid"),
    path("simulate_failed/<str:merchant_trade_no>/",simulate_failed,name="simulate_failed"),
    path("admin-tools/query/", db_query_tool, name="db_query_tool"),  # 新增
#     path("notify/", ecpay_notify, name="ecpay_notify"),        # 綠界 server-to-server 回傳
]
