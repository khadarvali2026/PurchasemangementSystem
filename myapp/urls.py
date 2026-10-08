from django.urls import path

from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('items/', views.item_list, name='item_list'),
    path('items/new/', views.item_create, name='item_create'),
    path('items/<int:pk>/', views.item_detail, name='item_detail'),
    path('items/<int:pk>/edit/', views.item_update, name='item_update'),
    path('items/<int:pk>/delete/', views.item_delete, name='item_delete'),
    path('types/', views.item_type_list, name='item_type_list'),
    path('types/new/', views.item_type_create, name='item_type_create'),
    path('types/<int:pk>/edit/', views.item_type_update, name='item_type_update'),
    path('types/<int:pk>/delete/', views.item_type_delete, name='item_type_delete'),
    path('purchases/', views.purchase_list, name='purchase_list'),
    path('purchases/new/', views.purchase_create, name='purchase_create'),
    path('purchases/<int:pk>/', views.purchase_detail, name='purchase_detail'),
    path('purchases/<int:pk>/edit/', views.purchase_update, name='purchase_update'),
]