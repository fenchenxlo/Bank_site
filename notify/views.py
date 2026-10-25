# ============================================================
# Bank_Mock/notify/views.py
# ============================================================
#
# 【架構說明】
#
# View 只負責：
#
# 1. 接收 HTTP Request
# 2. 解析 Request
# 3. 呼叫 Service
# 4. 將 Service 結果轉成 HTTP Response
#
# View 不負責：
#
# ❌ Django ORM
# ❌ VirtualAccount.objects
# ❌ httpx.post()
# ❌ 產生 bank_code
# ❌ 產生 v_account
# ❌ 產生 expire_date
# ❌ 呼叫 ECPay Mock
#
# 實際架構：
#
# View
#   ↓
# BankAccountService
#   ↓
# BankAccountGateway Interface
#   ↓
# BankAccountAdapter
#   ↓
# ORM / HTTPX
#
# ============================================================


import json, random, datetime
import logging
from util.ChkMacVal import generate_check_mac_value
from django.conf import settings

# ============================================================
# Django
# ============================================================

from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, JsonResponse, HttpResponseBadRequest
from util.ChkMacVal import generate_check_mac_value
from django.conf import settings
from .models import VirtualAccount          # 匯入 Order model，用來更新訂單狀態
from django.views.decorators.http import require_POST
import httpx ,json ,datetime 
from django.utils import timezone
from django.contrib.auth.decorators import user_passes_test
from django.db import transaction, IntegrityError, connection
from django.contrib import messages


# ============================================================
# Service / Adapter
# ============================================================

from .adapters.bank_account_adapter import BankAccountAdapter
from .services.bank_account_service import BankAccountService


# ============================================================
# Logger
# ============================================================

logger = logging.getLogger(__name__)


# ============================================================
# Service 初始化
# ============================================================
#
# 【保留】
#
# 明確建立：
#
# Adapter
#     ↓
# BankAccountService
#
# 目前專案規模下，
# 不另外增加 Factory / DI Container。
#
# ============================================================

def home(request):   
    return render(request, 'home.html')

def is_admin(user):
    """判斷是否為已登入的管理員(superuser)"""
    return user.is_authenticated and user.is_superuser
    

@user_passes_test(is_admin, login_url='/admin/login/')
def db_query_tool(request):
    """
    資料庫查詢工具:
    流程 —— 使用者先選擇 table,選定後列出該 table 所有欄位,
    再選擇「兩個」欄位(column1、column2),查詢這兩個欄位
    「同一列(同一筆資料)」對應的值,例如 order_number 對應 status。

    重點:兩個欄位必須放在同一個 SELECT 裡一起查,才能保證
    回傳的每一筆 (col1值, col2值) 確實來自同一列資料,
    而不是像分開查兩次那樣,兩份清單各自篩選、順序對不上。
    """
    tables = []          # 所有可查詢的 table 名稱
    columns = []          # 目前選定 table 的欄位名稱清單
    rows = []              # 查詢結果,每筆是 (col1值, col2值) 的 tuple
    error = None           # 查詢過程中若有錯誤,存放錯誤訊息

    table_choice = request.GET.get('table', '')      # 使用者選擇的 table 名稱
    column1_choice = request.GET.get('column1', '')  # 使用者選擇的第一個欄位
    column2_choice = request.GET.get('column2', '')  # 使用者選擇的第二個欄位

    with connection.cursor() as cursor:
        # 1. 取得資料庫中所有「業務用」table
        #    排除 sqlite 系統表、django 內建表、auth 相關表,避免查到不該看的系統資料
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' "
            "AND name NOT LIKE 'django_%' "
            "AND name NOT LIKE 'auth_%';"
        )
        tables = [r[0] for r in cursor.fetchall()]

        # 2. 若使用者有選擇 table,且該 table 確實存在於允許清單中
        #    (白名單檢查,防止使用者從網址列竄改 table 參數)
        if table_choice and table_choice in tables:
            # 2-1. 取得該 table 的所有欄位名稱(給使用者選擇用)
            cursor.execute(f"PRAGMA table_info({table_choice});")
            columns = [r[1] for r in cursor.fetchall()]

            # 3. 兩個欄位都要有選,且都存在於這個 table 的欄位清單中(白名單檢查),
            #    且不能選成同一個欄位(對應兩個一樣的東西沒有意義)
            if (column1_choice and column2_choice
                    and column1_choice in columns
                    and column2_choice in columns
                    and column1_choice != column2_choice):
                try:
                    # 3-1. 關鍵修改:col1、col2 放在同一個 SELECT 裡一起撈,
                    #      確保同一列回傳的兩個值是「同一筆資料」的對應值。
                    #      table_choice / column1_choice / column2_choice
                    #      都已經過白名單檢查,用 f-string 組 SQL 是安全的。
                    #      加上 ORDER BY rowid,確保每次查詢順序固定一致。
                    query = (
                        f"SELECT {column1_choice}, {column2_choice} "
                        f"FROM {table_choice} "
                        f"WHERE {column1_choice} IS NOT NULL "
                        f"AND {column2_choice} IS NOT NULL "
                        f"ORDER BY rowid;"
                    )
                    cursor.execute(query)
                    # 直接存成 tuple list:[(col1值, col2值), (col1值, col2值), ...]
                    rows = [(r[0], r[1]) for r in cursor.fetchall()]
                except Exception as e:
                    # 查詢過程中若發生錯誤(例如欄位型別問題),記錄錯誤訊息
                    error = str(e)

    context = {
        'tables': tables,
        'columns': columns,
        'rows': rows,
        'error': error,
        'table_choice': table_choice,
        'column1_choice': column1_choice,
        'column2_choice': column2_choice,
    }
    return render(request, 'admin_tools/db_query.html', context)

@csrf_exempt
@user_passes_test(is_admin, login_url='/admin/login/')
def query_and_simulate(request):
    """
    合併頁面:左側是 SQL 查詢工具(選 table -> 選欄位 -> 顯示該欄位所有非空值),
    右側是模擬銀行付款工具(手動輸入綠界交易編號,模擬「已收款」或「未收款」)。

    這是獨立的新頁面,跟原本的 db_query_tool 互不影響、互不共用邏輯,
    方便未來要單獨修改其中一個功能時,不會動到另一個。
    """
    tables = []
    columns = []
    rows = []
    error = None
    table_choice = request.GET.get('table', '')
    column_choice = request.GET.get('column', '')

    with connection.cursor() as cursor:
        # 1. 取得所有「業務用」table(排除系統表、django 內建表、auth 相關表)
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' "
            "AND name NOT LIKE 'django_%' "
            "AND name NOT LIKE 'auth_%';"
        )
        tables = [r[0] for r in cursor.fetchall()]

        # 2. 選了 table 且通過白名單檢查後,取得該 table 的所有欄位
        if table_choice and table_choice in tables:
            cursor.execute(f"PRAGMA table_info({table_choice});")
            columns = [r[1] for r in cursor.fetchall()]

            # 3. 選了欄位且通過白名單檢查後,查詢該欄位不為空的所有值
            if column_choice and column_choice in columns:
                try:
                    query = (
                        f"SELECT {column_choice} FROM {table_choice} "
                        f"WHERE {column_choice} IS NOT NULL;"
                    )
                    cursor.execute(query)
                    rows = [{column_choice: r[0]} for r in cursor.fetchall()]
                except Exception as e:
                    error = str(e)

    context = {
        'tables': tables,
        'columns': columns,
        'rows': rows,
        'error': error,
        'table_choice': table_choice,
        'column_choice': column_choice,
    }
    return render(request, 'admin_tools/query_simulate.html', context)

def get_bank_account_service():
    """
    建立 BankAccountService。

    【保留】

    Dependency Injection：

        BankAccountAdapter
                ↓
        BankAccountService
                ↓
              View
    """

    gateway = BankAccountAdapter()

    service = BankAccountService(
        gateway=gateway
    )

    return service


# ============================================================
# Home
# ============================================================

def home(request):
    """
    Bank Mock 首頁。

    【保留】

    此 View 不涉及資料庫。
    """

    return render(
        request,
        "home.html"
    )


# ============================================================
# 建立 ATM 虛擬帳號
# ============================================================

@csrf_exempt
def create_account(request):
    """
    建立 ATM 虛擬帳號。

    【保留 / 修改】

    View → Service → Interface → Adapter

    View 不直接操作 ORM 或 HTTPX。

    【修改】

    request_data 會完整傳遞到 Service，
    再由 Service 傳給 Gateway / Adapter，
    讓 Adapter 驗證 CheckMacValue。
    """

    # ========================================================
    # 【新增】
    # 只允許 POST
    # ========================================================

    if request.method != "POST":

        return JsonResponse(
            {
                "status": False,
                "message": "只允許 POST"
            },
            status=405
        )

    # ========================================================
    # 【新增】
    # 解析 JSON
    # ========================================================

    try:

        if not request.body:

            return JsonResponse(
                {
                    "status": False,
                    "message": "Request body 不可為空"
                },
                status=400
            )

        data = json.loads(
            request.body.decode("utf-8")
        )

    except json.JSONDecodeError:

        logger.warning(
            "Bank Mock create_account 收到無效 JSON"
        )

        return JsonResponse(
            {
                "status": False,
                "message": "JSON 格式錯誤"
            },
            status=400
        )

    except UnicodeDecodeError:

        logger.warning(
            "Bank Mock create_account 收到無效 UTF-8"
        )

        return JsonResponse(
            {
                "status": False,
                "message": "Request Body 編碼錯誤"
            },
            status=400
        )

    # ========================================================
    # 【新增】
    # 確認 JSON Object
    # ========================================================

    if not isinstance(data, dict):

        return JsonResponse(
            {
                "status": False,
                "message": "Request JSON 必須是 Object"
            },
            status=400
        )

    # ========================================================
    # 【新增】
    # 驗證 CheckMacValue
    #
    # 收到 data 後立即驗證，
    # 驗證成功才繼續往下執行。
    # ========================================================

    received_check_mac_value = data.get(
        "CheckMacValue"
    )

    if not received_check_mac_value:

        logger.warning(
            "Bank Mock create_account 缺少 CheckMacValue"
        )

        return JsonResponse(
            {
                "status": False,
                "message": "缺少 CheckMacValue"
            },
            status=400
        )

    verify_data = data.copy()

    verify_data.pop(
        "CheckMacValue",
        None
    )

    expected_check_mac_value = generate_check_mac_value(
        verify_data,
        settings.ECPAY_HASH_KEY,
        settings.ECPAY_HASH_IV
    )

    if received_check_mac_value != expected_check_mac_value:

        logger.warning(
            "Bank Mock create_account CheckMacValue 驗證失敗"
        )

        return JsonResponse(
            {
                "status": False,
                "message": "CheckMacValue 驗證失敗"
            },
            status=400
        )

    # ========================================================
    # 【新增】
    # 取得必要欄位
    # ========================================================

    merchant_trade_no = data.get(
        "merchant_trade_no"
    )

    trade_amt = data.get(
        "trade_amt"
    )

    # bank_code = data["bank_code"] = "013" # 國泰世華銀行代碼
    # v_account = data["v_account"] = f"013{random.randint(100000000000,999999999999)}" # 虛擬帳戶
    # expire_date = data["expire_date"] = (datetime.datetime.now() + datetime.timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
    data["bank_code"] = "013" # 國泰世華銀行代碼
    data["v_account"] = f"013{random.randint(100000000000,999999999999)}" # 虛擬帳戶
    data["expire_date"] = (datetime.datetime.now() + datetime.timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
    
    logging.info("bank_code=%s", data["bank_code"])
    logging.info("v_account=%s", data["v_account"])
    logging.info("expire_date=%s", data["expire_date"])
    
    # ========================================================
    # 【新增】
    # 基本 Request 驗證
    # ========================================================

    if not merchant_trade_no:

        return JsonResponse(
            {
                "status": False,
                "message": "缺少 merchant_trade_no"
            },
            status=400
        )

    if trade_amt in (None, ""):

        return JsonResponse(
            {
                "status": False,
                "message": "缺少 trade_amt"
            },
            status=400
        )

    # ========================================================
    # 【保留】
    # 明確初始化 Service
    # ========================================================

    service = get_bank_account_service()

    # ========================================================
    # 【修改】
    # 呼叫 Service
    #
    # request_data=data 必須傳下去。
    #
    # Service
    #     ↓
    # Gateway
    #     ↓
    # Adapter
    #     ↓
    # CheckMacValue
    # ========================================================

    try:
        logger.info(
            "data：%s",
            data
        )
        result = service.create_account(
            merchant_trade_no=merchant_trade_no,
            trade_amt=trade_amt,
            request_data=data,
        )

    except ValueError as ex:

        logger.warning(
            "Bank Mock create_account 業務驗證失敗：%s",
            ex
        )

        return JsonResponse(
            {
                "status": False,
                "message": str(ex)
            },
            status=400
        )

    except Exception as ex:

        logger.exception(
            "Bank Mock create_account 發生未預期錯誤"
        )

        return JsonResponse(
            {
                "status": False,
                "message": "Bank Mock 建立虛擬帳號失敗",
                "error": str(ex),
            },
            status=500
        )

    # ========================================================
    # 【保留】
    # 回傳結果
    # ========================================================

    return JsonResponse(
        result,
        status=200
    )


# ============================================================
# 查詢 ATM 虛擬帳號
# ============================================================

def account_detail(
    request,
    merchant_trade_no
):
    """
    顯示 ATM 虛擬帳號。

    【保留】

    View 不直接：

        VirtualAccount.objects.get()

    而是：

        View
          ↓
        Service
          ↓
        Gateway
          ↓
        Adapter
          ↓
        ORM
    """

    # ========================================================
    # 【新增】
    # 只允許 GET
    # ========================================================

    if request.method != "GET":

        return JsonResponse(
            {
                "status": False,
                "message": "只允許 GET"
            },
            status=405
        )

    # ========================================================
    # 【保留】
    # 明確初始化 Service
    # ========================================================

    service = get_bank_account_service()

    # ========================================================
    # 【保留】
    # 透過 Service 查詢
    # ========================================================

    try:

        result = service.get_account(
            merchant_trade_no=merchant_trade_no
        )

    except LookupError:

        return JsonResponse(
            {
                "status": False,
                "message": "找不到 ATM 虛擬帳號"
            },
            status=404
        )

    except ValueError as ex:

        return JsonResponse(
            {
                "status": False,
                "message": str(ex)
            },
            status=400
        )

    except Exception as ex:

        logger.exception(
            "Bank Mock account_detail 發生錯誤"
        )

        return JsonResponse(
            {
                "status": False,
                "message": "查詢 ATM 虛擬帳號失敗",
                "error": str(ex),
            },
            status=500
        )

    # ========================================================
    # 【保留】
    # Render
    #
    # 這裡可以直接把 Model 傳給 Template，
    # 因為 Template 可以處理 Django Model instance。
    #
    # 與 JsonResponse 不同。
    # ========================================================

    return render(
        request,
        "account_detail.html",
        {
            "account": result
        }
    )


# ============================================================
# 模擬 ATM 付款成功
# ============================================================

@csrf_exempt
def simulate_paid(
    request,
    merchant_trade_no
):
    """
    模擬 ATM 付款成功。

    【保留】

    View 不直接：

        ❌ ORM
        ❌ account.save()
        ❌ httpx.post()

    實際流程：

        View
          ↓
        Service
          ↓
        Gateway
          ↓
        Adapter
          ├── ORM
          └── HTTPX → ECPay Mock
    """

    # ========================================================
    # 【新增】
    # 允許 GET / POST
    # ========================================================

    if request.method not in ("GET", "POST"):

        return JsonResponse(
            {
                "status": False,
                "message": "只允許 GET 或 POST"
            },
            status=405
        )

    # ========================================================
    # 【保留】
    # 明確初始化 Service
    # ========================================================

    service = get_bank_account_service()

    # ========================================================
    # 【保留】
    # 呼叫 Service
    # ========================================================

    try:

        result = service.simulate_paid(
            merchant_trade_no=merchant_trade_no
        )

    except LookupError:

        return JsonResponse(
            {
                "status": False,
                "message": "找不到 ATM 虛擬帳號"
            },
            status=404
        )

    except ValueError as ex:

        logger.warning(
            "Bank Mock simulate_paid 業務錯誤：%s",
            ex
        )

        return JsonResponse(
            {
                "status": False,
                "message": str(ex)
            },
            status=400
        )

    except Exception as ex:

        logger.exception(
            "Bank Mock simulate_paid 發生未預期錯誤"
        )

        return JsonResponse(
            {
                "status": False,
                "message": "模擬付款成功失敗",
                "error": str(ex),
            },
            status=500
        )

    # ========================================================
    # 【修改】
    # 回傳 Service 結果
    #
    # Service 現在已經把 VirtualAccount
    # 轉成 JSON-safe dict。
    #
    # 因此這裡不會再發生：
    #
    # TypeError:
    # Object of type VirtualAccount
    # is not JSON serializable
    # ========================================================

    return JsonResponse(
        result,
        status=200
    )


# ============================================================
# 模擬 ATM 付款失敗
# ============================================================

@csrf_exempt
def simulate_failed(
    request,
    merchant_trade_no
):
    """
    模擬 ATM 付款失敗。

    【保留】

    View 不直接操作 ORM，也不直接呼叫 HTTPX。

    目前 VirtualAccount 沒有 failed status，
    因此：

        Bank DB 不修改成 failed

    只將：

        status = failed

    callback 給 ECPay Mock。

    ECPay Mock 再決定如何處理 Store Payment。
    """

    # ========================================================
    # 【新增】
    # 允許 GET / POST
    # ========================================================

    if request.method not in ("GET", "POST"):

        return JsonResponse(
            {
                "status": False,
                "message": "只允許 GET 或 POST"
            },
            status=405
        )

    # ========================================================
    # 【保留】
    # 明確初始化 Service
    # ========================================================

    service = get_bank_account_service()

    # ========================================================
    # 【保留】
    # 呼叫 Service
    # ========================================================

    try:

        result = service.simulate_failed(
            merchant_trade_no=merchant_trade_no
        )

    except LookupError:

        return JsonResponse(
            {
                "status": False,
                "message": "找不到 ATM 虛擬帳號"
            },
            status=404
        )

    except ValueError as ex:

        logger.warning(
            "Bank Mock simulate_failed 業務錯誤：%s",
            ex
        )

        return JsonResponse(
            {
                "status": False,
                "message": str(ex)
            },
            status=400
        )

    except Exception as ex:

        logger.exception(
            "Bank Mock simulate_failed 發生未預期錯誤"
        )

        return JsonResponse(
            {
                "status": False,
                "message": "模擬付款失敗",
                "error": str(ex),
            },
            status=500
        )

    # ========================================================
    # 【修改】
    # 回傳 Service 結果
    #
    # Service 已將 VirtualAccount
    # 轉成 JSON-safe dict。
    # ========================================================

    return JsonResponse(
        result,
        status=200
    )


# ============================================================
# 【新增】模擬 ATM 逾期未付款
#
# 只負責收 request / 回 JSON，不碰 ORM，
# 實際流程在 BankAccountService.simulate_expired。
# 錯誤處理與 simulate_failed 一致。
# ============================================================
# 【新增】必須加 @csrf_exempt（與 simulate_paid / simulate_failed 相同），
# 否則頁面用 fetch POST 會被 CSRF 擋下回 403，前端就會解析 HTML 失敗
@csrf_exempt
def simulate_expired(request, merchant_trade_no):

    if request.method not in ("GET", "POST"):
        return JsonResponse(
            {"status": False, "message": "只允許 GET 或 POST"},
            status=405
        )

    service = get_bank_account_service()

    try:
        result = service.simulate_expired(
            merchant_trade_no=merchant_trade_no
        )
    except LookupError:
        return JsonResponse(
            {"status": False, "message": "找不到 ATM 虛擬帳號"},
            status=404
        )
    except ValueError as ex:
        logger.warning("Bank Mock simulate_expired 業務錯誤：%s", ex)
        return JsonResponse(
            {"status": False, "message": str(ex)},
            status=400
        )
    except Exception as ex:
        logger.exception("Bank Mock simulate_expired 發生未預期錯誤")
        return JsonResponse(
            {"status": False, "message": "模擬逾期未付款失敗", "error": str(ex)},
            status=500
        )

    return JsonResponse(result, status=200)


# ============================================================
# 【新增】取消 ATM 虛擬帳號
# ECPay Mock → Bank Mock（server-to-server，POST JSON + CheckMacValue）
# View 只收 request / 回 JSON，不碰 ORM；流程在 BankAccountService.cancel_account
# ============================================================
@csrf_exempt
def cancel_account(request, merchant_trade_no):

    if request.method != "POST":
        return JsonResponse(
            {"status": False, "message": "只允許 POST"},
            status=405
        )

    try:
        data = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse(
            {"status": False, "message": "JSON 格式錯誤"},
            status=400
        )

    service = get_bank_account_service()

    try:
        result = service.cancel_account(
            merchant_trade_no=merchant_trade_no,
            request_data=data,
        )
    except LookupError:
        return JsonResponse(
            {"status": False, "message": "找不到 ATM 虛擬帳號"},
            status=404
        )
    except ValueError as ex:
        logger.warning("Bank Mock cancel_account 業務錯誤：%s", ex)
        return JsonResponse(
            {"status": False, "message": str(ex)},
            status=400
        )
    except Exception as ex:
        logger.exception("Bank Mock cancel_account 發生未預期錯誤")
        return JsonResponse(
            {"status": False, "message": "取消 ATM 帳號失敗", "error": str(ex)},
            status=500
        )

    return JsonResponse(result, status=200)