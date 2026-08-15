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
from django.db import connection
import logging          # 【新增】

logger = logging.getLogger(__name__)   # 【新增】

# Create your views here.

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


# 銀行接收 Callback ,create_account
@csrf_exempt
def create_account(request):
    
    if request.method != "POST":
        return HttpResponse("method error")

    try:
#         if request.content_type == "application/json":
#             payment_data = json.loads(request.body.decode("utf-8"))
            
        data = request.POST.dict() if request.POST else request.body
            # 如果商城端用 JSON 傳送
        if isinstance(data, (bytes, bytearray)):
            data = json.loads(data.decode("utf-8"))
            print("1")
            logger.info("1")
#            payment_data  = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return HttpResponseBadRequest("JSON 格式錯誤")
#    payment_data = request.POST.dict()

#     recv_mac = payment_data.copy()
    
    recv_mac = data.pop("CheckMacValue", "")

    local_mac = generate_check_mac_value(
        data,
        settings.ECPAY_HASH_KEY,
        settings.ECPAY_HASH_IV
    )
    
#     print("recv_mac =", recv_mac)
#     print("local_mac =", local_mac)
#     print("data =", data)

    if recv_mac != local_mac:
        return JsonResponse({
            "status":"error",
            "message":"MAC驗證失敗"
        }, status=400)
    
    print("data['expire_date']: ",data["expire_date"])
    print("data['expire_date']: ",type(data["expire_date"]))
#     expire_date = datetime.strptime(data["expire_date"], "%Y-%m-%d %H:%M:%S")
#     expire_date = timezone.make_aware(expire_date)
    print("2")
    logger.info("2")
    expire_date = timezone.make_aware(
        datetime.datetime.strptime(
            data["expire_date"],
            "%Y-%m-%d %H:%M:%S"
        )
    )
    try:
        # 嘗試取得VirtualAccount，如果沒有就建立
        virtual_account, created = VirtualAccount.objects.get_or_create(
            merchant_trade_no=data["merchant_trade_no"],
            defaults={'bank_code': data["bank_code"],
                      'v_account': data["v_account"],
                      'trade_amt': data["trade_amt"],
#                       'expire_date': expire_date,
                      'expire_date': expire_date,
                      'status': data["status"],
                    }
        )
    except Exception as ex:

        print("銀行通知失敗: 虛擬帳號 取得或建立失敗")
        logger.info("銀行通知失敗: 虛擬帳號 取得或建立失敗")
        print(ex)
        logger.info(f"Exception as ex: {ex}")
        return JsonResponse({"status":False, "message": "虛擬帳號建立失敗" }, status=500)
    logger.info("3")
    print("3")
    
    return JsonResponse({ "status":True,
        "merchant_trade_no": virtual_account.merchant_trade_no,
        "bank_code": virtual_account.bank_code,
        "v_account": virtual_account.v_account,
        "expire_date": virtual_account.expire_date.strftime("%Y-%m-%d %H:%M:%S"),
        "trade_amt": str(virtual_account.trade_amt),
        "payment_status": virtual_account.status
    })

@csrf_exempt
def account_detail(request, merchant_trade_no):
    
    # 取得account
    account = get_object_or_404(VirtualAccount,merchant_trade_no=merchant_trade_no)
#     account = (
#         
#         VirtualAccount.objects.get(
#             merchant_trade_no=merchant_trade_no
#         )
#     )

    return render(request, "account_detail.html", {"account": account})

@csrf_exempt
def simulate_paid(request, merchant_trade_no):

    account = VirtualAccount.objects.get(merchant_trade_no=merchant_trade_no)

    account.status = "paid"

    account.save()

    payload = {
        "merchant_trade_no": account.merchant_trade_no,
        "trade_amt": int(account.trade_amt),
        "bank_code": account.bank_code,
        "v_account": account.v_account,
        "expire_date": account.expire_date.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "paid",
#         "created_at": account.created_at.strftime("%Y-%m-%d %H:%M:%S"),
    }

    payload["CheckMacValue"] = (
        generate_check_mac_value(payload,settings.ECPAY_HASH_KEY,settings.ECPAY_HASH_IV)
    )

    try:        
        response = httpx.post(

#            "http://127.0.0.1:8001/gateway/payment_notify/",
            f"{settings.HF_SPACE_ECPAY_MOCK_URL}/gateway/payment_notify/",

            json=payload,

            timeout=10
        )

        print("status_code =", response.status_code)
        print("response.text =", response.text)
            
        if response.status_code != 200:
            return JsonResponse({
                "status": False,
                "error": response.text
            }, status=400)

            print("1")
            
            # 👇 建議統一 API 回 JSON，不要 render
            return JsonResponse({
                "status": True,
                "gateway_response": response.json()
            })
        else:
            return render(request, "admin_tools/db_query.html", {'account':payload})
#            return render(request, "account_detail.html", {'account':payload})
#             return redirect(
#                 f"notify/account_detail/{account}/"
#             )
    except Exception as ex:

        print("綠界通知失敗")
        print(ex)
        
        return JsonResponse({
            "status": False,
            "message": str(ex)
        }, status=500)
    
    return JsonResponse({
            "status":True
    })

@csrf_exempt
def simulate_failed(request, merchant_trade_no):

    account = VirtualAccount.objects.get(merchant_trade_no=merchant_trade_no)
    
    account.status = "failed"

    account.save()
    
    payload = {
        "merchant_trade_no": account.merchant_trade_no,
        "trade_amt": str(account.trade_amt),
        "bank_code": account.bank_code,
        "v_account": account.v_account,
        "expire_date": account.expire_date.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "failed",
#         "created_at": account.created_at.strftime("%Y-%m-%d %H:%M:%S"),
    }

    payload["CheckMacValue"] = (
        generate_check_mac_value(payload,settings.ECPAY_HASH_KEY,settings.ECPAY_HASH_IV)
    )
    
    try:        
        response = httpx.post(

#            "http://127.0.0.1:8001/gateway/payment_notify/",
            f"{settings.HF_SPACE_ECPAY_MOCK_URL}/gateway/payment_notify/",
            json=payload,

            timeout=10
        )

        print("status_code =", response.status_code)
        print("response.text =", response.text)
            
        if response.status_code != 200:
            return {
                "status": False,
                "message": str(response.text)
            }

            print("2")
            
            # 👇 建議統一 API 回 JSON，不要 render
            return JsonResponse({
                "status": True,
                "gateway_response": response.json()
            })
        else:
            return render(request, "admin_tools/db_query.html", {'account':payload})
#            return render(request, "account_detail.html", {'account':payload})
#             return redirect(
#                 f"notify/account_detail/{account}/"
#             )
    except Exception as ex:

        print("綠界通知失敗")
        print(ex)
        
        return {
            "status": False,
            "message": str(ex)
        }
    
    return JsonResponse({
            "status":True
    })

#     return redirect(
#         f"notify/account_detail/{account.merchant_trade_no}/"
#     )

