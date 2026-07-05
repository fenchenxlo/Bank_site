from django.shortcuts import render, get_object_or_404, redirect
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

        print("銀行通知失敗: 虛擬帳號 取得或建立失敗")

        print(ex)
        
        return ({"status":False })
    print("3")
    return JsonResponse({ "status":True})

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
        "trade_amt": str(account.trade_amt),
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

            "http://127.0.0.1:8001/gateway/payment_notify/",

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
            return render(request, "account_detail.html", {'account':payload})
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

            "http://127.0.0.1:8001/gateway/payment_notify/",

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
            return render(request, "account_detail.html", {'account':payload})
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

