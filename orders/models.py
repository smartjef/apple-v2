from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from shop.models import Product
# Create your models here.


class Order(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='order')
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    paid = models.BooleanField(default=False)

    def __str__(self):
        return f'Order {self.id}'

    class Meta:
        ordering = ['-created']
        indexes = [
            models.Index(fields=['-created']),
        ]

    def get_amount_paid(self):
        return sum(payment.items.amount for payment in Payment.objects.filter(order=self))

    def get_total_cost(self):
        return sum(item.get_cost() for item in self.items.all())

    def get_balance(self):
        return self.get_total_cost() - self.get_amount_paid()


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='order_items')
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)

    def __str__(self):
        return str(self.product)

    def get_cost(self):
        return self.price * self.quantity


class Payment(models.Model):
    order = models.ForeignKey(Order, related_name="payment", on_delete=models.CASCADE)
    merchant_request_id = models.CharField(max_length=100)
    checkout_request_id = models.CharField(max_length=100)
    result_code = models.IntegerField()
    result_description = models.TextField()
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.order}'s Payment"


class PaymentDetails(models.Model):
    payment = models.OneToOneField(Payment, related_name='items', on_delete=models.CASCADE)
    mpesa_receipt_number = models.CharField(max_length=100, null=True, blank=True)
    transaction_date = models.CharField(max_length=256, null=True, blank=True)
    phone_number = models.CharField(max_length=13, blank=True, null=True)
    amount = models.DecimalField(max_digits=11, decimal_places=2)


@receiver(post_save, sender=PaymentDetails)
def check_if_payment_complete_and_mark_paid(sender, instance, created, **kwargs):
    if created:
        # update order payment status to true if balance is o
        _order = instance.payment.order
        if _order.get_balance() <= 0.95:
            _order.paid = True
            _order.save()
        else:
            _order.paid = False
            _order.save()
