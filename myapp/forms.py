from django import forms
from django.core.exceptions import ValidationError
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.db.models import Q

from .models import Item, ItemType, Purchase, PurchaseItem


class ItemTypeForm(forms.ModelForm):
    class Meta:
        model = ItemType
        fields = ['name', 'description']
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}


class ItemForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['stock'].label = 'Current stock' if self.instance.pk else 'Initial stock'

    class Meta:
        model = Item
        fields = ['item_type', 'name', 'sku', 'purchase_date', 'description', 'unit_price', 'stock', 'is_active']
        widgets = {
            'purchase_date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 3}),
            'unit_price': forms.NumberInput(attrs={'min': '0', 'step': '0.01'}),
            'stock': forms.NumberInput(attrs={'min': '0', 'step': '1'}),
        }


class PurchaseForm(forms.ModelForm):
    class Meta:
        model = Purchase
        fields = ['customer_name']


class PurchaseItemForm(forms.ModelForm):
    quantity = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={'min': '1', 'step': '1'}),
    )

    class Meta:
        model = PurchaseItem
        fields = ['item', 'quantity']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = Item.objects.filter(is_active=True)
        if self.instance.pk and self.instance.item_id:
            queryset = Item.objects.filter(Q(is_active=True) | Q(pk=self.instance.item_id))
        self.fields['item'].queryset = queryset.order_by('name')


class BasePurchaseItemFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return

        selected_items = []
        for form in self.forms:
            if not hasattr(form, 'cleaned_data') or form.cleaned_data.get('DELETE'):
                continue
            item = form.cleaned_data.get('item')
            quantity = form.cleaned_data.get('quantity')
            if item and quantity:
                selected_items.append(item.pk)

        if len(selected_items) != len(set(selected_items)):
            raise ValidationError('Add each item once and adjust its quantity on that line.')


PurchaseItemFormSet = inlineformset_factory(
    Purchase,
    PurchaseItem,
    form=PurchaseItemForm,
    formset=BasePurchaseItemFormSet,
    fields=['item', 'quantity'],
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True,
)