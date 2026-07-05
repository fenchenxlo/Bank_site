from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, JsonResponse, HttpResponseBadRequest
from util.ChkMacVal import generate_check_mac_value
from django.conf import settings
from .models import VirtualAccount          # 匯入 Order model，用來更新訂單狀態
from django.views.decorators.http import require_POST
import httpx ,json ,datetime 
from django.utils import timezone

# Create your views here.
def home(request):   
    return render(request, 'home.html')

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
#            payment_data  = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return HttpResponseBadRequest("JSON 格式錯誤")
#    payment_data = request.POST.dict()

#     recv_mac = payment_data.copy()
    
    recv_mac = data.pop("CheckMacValue")

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
    
    try:
        # 嘗試取得VirtualAccount，如果沒有就建立
        virtual_account, created = VirtualAccount.objects.get_or_create(
            merchant_trade_no=data["merchant_trade_no"],
            defaults={'bank_code': data["bank_code"],
                      'v_account': data["v_account"],
                      'trade_amt': data["trade_amt"],
#                       'expire_date': expire_date,
                      'expire_date': data['expire_date'],
                      'status': data["status"],
                    }
        )
    except Exception as ex:

        print("銀行通知失敗: VirtualAccount取得或建立失敗")

        print(ex)
        
        return JsonResponse({

            "status":"failed"

        })

    return JsonResponse({

        "status":"success"

    })

def account_detail(request, merchant_trade_no):
    
    # 取得account
    account = get_object_or_404(VirtualAccount, merchant_trade_no=merchant_trade_no)
#     account = (
#         
#         VirtualAccount.objects.get(
#             merchant_trade_no=merchant_trade_no
#         )
#     )

    return render(request, "account_detail.html", {"account": account})

def simulate_paid(request, pk):

    account = VirtualAccount.objects.get(pk=pk)

    account.status = "paid"

    account.save()

    payload = {
        "merchant_trade_no": account.merchant_trade_no,
        "trade_amt": int(account.trade_amt),
        "bank_code": account.bank_code,
        "v_account": account.v_account,
        "status": "paid"
    }

    payload["CheckMacValue"] = (
        generate_check_mac_value(payload)
    )

    response = httpx.post(

        "http://127.0.0.1:8001/api/payment-notify/",

        json=payload,

        timeout=10
    )

    print(response.text)

    return redirect(
        f"/account/{account.merchant_trade_no}/"
    )

def simulate_failed(request, pk):

    account = VirtualAccount.objects.get(pk=pk)

    payload = {
        "merchant_trade_no": account.merchant_trade_no,
        "trade_amt": int(account.trade_amt),
        "bank_code": account.bank_code,
        "v_account": account.v_account,
        "status": "failed"
    }

    payload["CheckMacValue"] = (
        generate_check_mac_value(payload)
    )

    response = httpx.post(

        "http://127.0.0.1:8001/api/payment-notify/",

        json=payload,

        timeout=10
    )

    print(response.text)

    return redirect(
        f"/account/{account.merchant_trade_no}/"
    )

