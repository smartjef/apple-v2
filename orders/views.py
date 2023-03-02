from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import Http404
from django.shortcuts import render, redirect
from django.shortcuts import reverse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from cart.cart_wish import CartWish
from orders.models import OrderItem, Order, PaymentDetails, Payment
from django.shortcuts import get_object_or_404
from django.utils.timezone import datetime
from orders.payment.payment import MpesaClient
from root.breadcrumb import BreadCrumb
# Create your views here.


def order_create(request):
    cart = CartWish(request)
    if cart.length_cart():
        order = Order.objects.create(user=request.user)
        for item in cart.iter_cart():
            OrderItem.objects.create(
                order=order,
                product=item['product'],
                price=item['price'],
                quantity=item['quantity']
            )
        # clear the cart
        cart.clear_cart()
        messages.success(request,  f"Your New order ORD-{order.created.year}-{order.id} created successfully!"
                                   f"We will get back to you soon")
        # TODO NOTIFY ADMINS AND SEND INVOICE TO USER
        return redirect(
            reverse('order:order_details', args=[order.id])
        )
    return redirect('shop:product_list')


@login_required
def order_history(request):
    bread_crumb = [
        BreadCrumb("Home", "/"),
        BreadCrumb("Shop", reverse('shop:product_list')),
        BreadCrumb("Orders", reverse('order:order_history'), True),
    ]
    orders = Order.objects.filter(user=request.user)
    return render(request, 'order/order_history.html', {'orders': orders, 'bread_crumb': bread_crumb})


@login_required
def view_order_details(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    bread_crumb = [
        BreadCrumb("Home", "/"),
        BreadCrumb("Shop", reverse('shop:product_list')),
        BreadCrumb("Orders", reverse('order:order_history')),
        BreadCrumb(f"ORD-{order_id}", reverse('order:order_details', args=[order_id]), True),
    ]
    return render(request, 'order/order_details.html', {"order": order, "bread_crumb": bread_crumb})


@login_required
def order_payment_history(request, order_id):
    bread_crumb = [
        BreadCrumb("Home", "/"),
        BreadCrumb("Shop", reverse('shop:product_list')),
        BreadCrumb("Orders", reverse('order:order_history')),
        BreadCrumb(f"ORD-{order_id}", reverse('order:order_details', args=[order_id])),
        BreadCrumb(f"Payment history", reverse('order:order_payment_history', args=[order_id]), True),
    ]
    order = get_object_or_404(Order, id=order_id, user=request.user)
    return render(request, "order/payment_history.html", {"bread_crumb": bread_crumb, "order": order})

@login_required
def view_invoice(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    return render(request, 'order/pdf.html', {"order": order})


@staff_member_required
def admin_order_detail(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    return render(request,
                  'admin/orders/order/detail.html',
                  {'order': order})


@login_required
def make_payment(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    # payment.SHORT_CODE = settings.SHORT_CODE
    # payment.PASSKEY = settings.PASSKEY
    # payment.CONSUMER_SECRET = settings.CONSUMER_SECRET
    # payment.CONSUMER_KEY = settings.CONSUMER_KEY
    # payment.ACCOUNT_TYPE = settings.ACCOUNT_TYPE

    client_builder = MpesaClient.Builder()
    client = client_builder.add_credentials(
        consumer_key=settings.CONSUMER_KEY,
        consumer_secret=settings.CONSUMER_SECRET,
        pass_key=settings.PASSKEY
    ).add_business_name(settings.BUSINESS_NAME).add_business_short_code(
        settings.SHORT_CODE
    ).add_call_back_url(
        f"{request.scheme}://{request.get_host}" +
        reverse(
            'api:order_payment',
            args=[order_id]
        )
    ).add_description(
        'Payment gor goods ordered'
    ).build()
    details = client.trigger_stk_push(
        phone_number=int(str(request.user.userprofile.phone).strip('+')),
        amount=order.get_total_cost(),
    )
    return render(request, "order/payment.html", {"details": details})


def make_manual_payment(request):
    if not request.user.is_staff:
        raise Http404
    order = None
    if request.method == 'POST':
        order_id = request.POST.get('order_id')
        try:
            order_id = int(order_id)
            order = get_object_or_404(Order, id=order_id)
        except ValueError:
            messages.warning(request, f"The order id entered {order_id} is Invalid")
        except Http404:
            messages.warning(request, f"No order with id {order_id}")
    return render(request, 'order/manual_payment.html', {"order": order})


@require_POST
def create_transaction(request, order_id):
    if not request.user.is_staff:
        raise Http404
    id_ = request.POST.get("transaction_id")
    order = get_object_or_404(Order, id=order_id)
    if order.paid:
        messages.warning(request, f"Order ORD-{order.id} is already paid!")
        return redirect('order:make_manual_payment')
    new_payment = Payment(
        order=order,
        merchant_request_id=f"ORDRQ-{datetime.now().year}-{order.id}-{id_}",
        checkout_request_id=f"ORDRP-{datetime.now().year}-{order_id}-{id_}",
        result_code=0,
        result_description=f"Customer paid on delivery by user {request.user}",
    )
    new_payment.save()
    payment_detail = PaymentDetails(
        payment=new_payment,
        amount=order.get_total_cost(),
        mpesa_receipt_number=id_,
        transaction_date=str(datetime.now()),
        phone_number=str(order.user.userprofile.phone)
    )
    payment_detail.save()
    messages.success(request, f"Payment Was Successful for transaction {payment_detail.mpesa_receipt_number}")
    return render(request, 'order/manual_payment.html', {"order": order})
