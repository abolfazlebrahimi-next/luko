from django.urls import path

from . import views

urlpatterns = [
    path("plans", views.PlansView.as_view(), name="billing-plans"),
    path("children", views.ChildrenStatusView.as_view(), name="billing-children"),
    path("payments", views.PaymentsView.as_view(), name="billing-payments"),
    path("payments/<int:pk>", views.PaymentDetailView.as_view(), name="billing-payment"),
    path("checkout", views.CheckoutView.as_view(), name="billing-checkout"),
    path("bazaar/verify", views.BazaarVerifyView.as_view(), name="billing-bazaar-verify"),
    path("callback", views.CallbackView.as_view(), name="billing-callback"),
    path("callback/zibal", views.ZibalCallbackView.as_view(), name="billing-callback-zibal"),
    path("zibal/go/<str:track_id>", views.ZibalGoView.as_view(), name="billing-zibal-go"),
]
