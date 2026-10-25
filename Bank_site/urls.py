"""
URL configuration for Bank_site project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView   # 【新增】首頁轉址
# from notify.views import (
#     home,
# )

urlpatterns = [
    # 【新增】進入 127.0.0.1:8002/ 時，自動轉到 ATM 查詢 + 模擬付款頁
    path(
        "",
        RedirectView.as_view(
            pattern_name="notify:query_and_simulate",
            permanent=False,
        ),
        name="root_redirect",
    ),
#     path('', home, name='home'),
    path('admin/', admin.site.urls),
    path("notify/", include("notify.urls")),  # 把 notify app 的 urls 串進來
]
