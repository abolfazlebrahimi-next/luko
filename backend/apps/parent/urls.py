from django.urls import path

from . import account, views, referrals

urlpatterns = [
    path("referral", referrals.ReferralView.as_view(), name="parent-referral"),
    path("referral/rewards/<int:reward_id>/redeem", referrals.RedeemReferralRewardView.as_view(), name="referral-redeem"),
    path("children", views.ChildrenView.as_view(), name="parent-children"),
    path("children/<int:child_id>", views.ChildDetailView.as_view(), name="parent-child"),
    path("children/<int:child_id>/profile", account.ChildProfileView.as_view(), name="parent-child-profile"),
    path("password", account.ParentPasswordView.as_view(), name="parent-password"),
    path("children/<int:child_id>/report", views.ChildReportView.as_view(),
         name="parent-child-report"),
    path("children/<int:child_id>/password", views.ChildPasswordView.as_view(),
         name="parent-child-password"),
    path("children/<int:child_id>/phone/start", views.ChildPhoneStartView.as_view(),
         name="parent-child-phone-start"),
    path("children/<int:child_id>/phone/confirm", views.ChildPhoneConfirmView.as_view(),
         name="parent-child-phone-confirm"),
    path("children/<int:child_id>/assignments", views.AssignmentsView.as_view(),
         name="parent-assignments"),
    path("children/<int:child_id>/assignments/<int:pk>", views.AssignmentDetailView.as_view(),
         name="parent-assignment"),
    path("children/<int:child_id>/suggestions", views.SuggestionsView.as_view(),
         name="parent-suggestions"),
    path("preferences", views.PreferenceView.as_view(), name="parent-preferences"),
    path("notifications", views.NotificationsView.as_view(), name="parent-notifications"),
    path("notifications/read", views.NotificationsReadView.as_view(),
         name="parent-notifications-read"),
]
