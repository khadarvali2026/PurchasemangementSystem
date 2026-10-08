from collections import defaultdict

from django.contrib import messages
from django.db import transaction
from django.db.models import Exists, OuterRef, Prefetch
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ItemForm, ItemTypeForm, PurchaseForm, PurchaseItemFormSet
from .models import Item, ItemType, Purchase, PurchaseItem


def dashboard(request):
	context = {
		'item_count': Item.objects.count(),
		'active_item_count': Item.objects.filter(is_active=True).count(),
		'purchase_count': Purchase.objects.count(),
		'recent_purchases': Purchase.objects.prefetch_related('lines__item')[:5],
		'low_stock_items': Item.objects.filter(is_active=True, stock__lte=5)[:5],
	}
	return render(request, 'myapp/dashboard.html', context)


def item_list(request):
	items = Item.objects.select_related('item_type').annotate(
		has_purchase_history=Exists(PurchaseItem.objects.filter(item_id=OuterRef('pk'))),
	)
	return render(request, 'myapp/item_list.html', {'items': items})


def item_detail(request, pk):
	item = get_object_or_404(
		Item.objects.select_related('item_type').prefetch_related(
			Prefetch(
				'purchase_lines',
				queryset=PurchaseItem.objects.select_related('purchase').order_by('-purchase__created_at'),
			),
		),
		pk=pk,
	)
	purchase_lines = list(item.purchase_lines.all())
	return render(request, 'myapp/item_detail.html', {
		'item': item,
		'purchase_lines': purchase_lines,
		'has_purchase_history': bool(purchase_lines),
	})


def item_create(request):
	form = ItemForm(request.POST or None)
	if request.method == 'POST' and form.is_valid():
		form.save()
		messages.success(request, 'Item created.')
		return redirect('item_list')
	return render(request, 'myapp/item_form.html', {'form': form, 'title': 'Add item'})


def item_update(request, pk):
	item = get_object_or_404(Item, pk=pk)
	form = ItemForm(request.POST or None, instance=item)
	if request.method == 'POST' and form.is_valid():
		form.save()
		messages.success(request, 'Item updated.')
		return redirect('item_list')
	return render(request, 'myapp/item_form.html', {'form': form, 'title': 'Edit item'})


def item_delete(request, pk):
	if request.method == 'POST':
		try:
			with transaction.atomic():
				item = get_object_or_404(Item.objects.select_for_update(), pk=pk)
				if item.purchase_lines.exists():
					messages.error(request, 'This item has purchase history and cannot be deleted. Deactivate it instead.')
					return redirect('item_detail', pk=item.pk)
				item.delete()
		except ProtectedError:
			messages.error(request, 'This item is protected by purchase history and cannot be deleted. Deactivate it instead.')
			return redirect('item_detail', pk=pk)
		messages.success(request, 'Item deleted.')
		return redirect('item_list')

	item = get_object_or_404(Item, pk=pk)
	if item.purchase_lines.exists():
		messages.error(request, 'This item has purchase history and cannot be deleted. Deactivate it instead.')
		return redirect('item_detail', pk=item.pk)
	return render(request, 'myapp/confirm_delete.html', {'object': item, 'title': 'Delete item'})


def item_type_list(request):
	types = ItemType.objects.prefetch_related('items').all()
	return render(request, 'myapp/item_type_list.html', {'item_types': types})


def item_type_create(request):
	form = ItemTypeForm(request.POST or None)
	if request.method == 'POST' and form.is_valid():
		form.save()
		messages.success(request, 'Item type created.')
		return redirect('item_type_list')
	return render(request, 'myapp/item_type_form.html', {'form': form, 'title': 'Add item type'})


def item_type_update(request, pk):
	item_type = get_object_or_404(ItemType, pk=pk)
	form = ItemTypeForm(request.POST or None, instance=item_type)
	if request.method == 'POST' and form.is_valid():
		form.save()
		messages.success(request, 'Item type updated.')
		return redirect('item_type_list')
	return render(request, 'myapp/item_type_form.html', {'form': form, 'title': 'Edit item type'})


def item_type_delete(request, pk):
	item_type = get_object_or_404(ItemType, pk=pk)
	if request.method == 'POST':
		if item_type.items.exists():
			messages.error(request, 'This type still has items and cannot be deleted.')
		else:
			item_type.delete()
			messages.success(request, 'Item type deleted.')
		return redirect('item_type_list')
	return render(request, 'myapp/confirm_delete.html', {'object': item_type, 'title': 'Delete item type'})


def purchase_list(request):
	purchases = Purchase.objects.prefetch_related('lines__item').all()
	return render(request, 'myapp/purchase_list.html', {'purchases': purchases})


def purchase_detail(request, pk):
	purchase = get_object_or_404(
		Purchase.objects.prefetch_related('lines__item__item_type'),
		pk=pk,
	)
	return render(request, 'myapp/purchase_detail.html', {'purchase': purchase})


def _purchase_forms(request, purchase=None):
	form = PurchaseForm(request.POST or None, instance=purchase)
	formset = PurchaseItemFormSet(request.POST or None, instance=purchase, prefix='lines')
	return form, formset


def purchase_create(request):
	form, formset = _purchase_forms(request)
	if request.method == 'POST' and form.is_valid() and formset.is_valid():
		desired = defaultdict(int)
		for line_form in formset.forms:
			data = getattr(line_form, 'cleaned_data', {})
			if data and not data.get('DELETE') and data.get('item'):
				desired[data['item'].pk] += data['quantity']

		with transaction.atomic():
			locked_items = {
				item.pk: item
				for item in Item.objects.select_for_update().filter(pk__in=desired).order_by('pk')
			}
			error = _stock_error(desired, locked_items)
			if error:
				return render(request, 'myapp/purchase_form.html', {
					'form': form, 'formset': formset, 'title': 'New purchase', 'stock_error': error,
				})

			purchase = form.save()
			for line_form in formset.forms:
				data = getattr(line_form, 'cleaned_data', {})
				if not data or data.get('DELETE') or not data.get('item'):
					continue
				item = locked_items[data['item'].pk]
				item.stock -= data['quantity']
				item.save(update_fields=['stock'])
				PurchaseItem.objects.create(
					purchase=purchase,
					item=item,
					quantity=data['quantity'],
					unit_price=item.unit_price,
				)

		messages.success(request, f'{purchase.order_number} recorded and stock updated.')
		return redirect('purchase_detail', pk=purchase.pk)
	return render(request, 'myapp/purchase_form.html', {
		'form': form, 'formset': formset, 'title': 'New purchase',
	})


def purchase_update(request, pk):
	if request.method == 'POST':
		with transaction.atomic():
			purchase = get_object_or_404(Purchase.objects.select_for_update(), pk=pk)
			form, formset = _purchase_forms(request, purchase)
			if form.is_valid() and formset.is_valid():
				desired = defaultdict(int)
				previous = defaultdict(int)
				original_lines = list(PurchaseItem.objects.select_for_update().filter(purchase=purchase))
				for line in original_lines:
					previous[line.item_id] += line.quantity
				for line_form in formset.forms:
					data = getattr(line_form, 'cleaned_data', {})
					if data and not data.get('DELETE') and data.get('item'):
						desired[data['item'].pk] += data['quantity']

				affected_ids = set(previous) | set(desired)
				locked_items = {
					item.pk: item
					for item in Item.objects.select_for_update().filter(pk__in=affected_ids).order_by('pk')
				}
				error = _stock_error(desired, locked_items, previous)
				if not error:
					form.save()
					for item_id in affected_ids:
						item = locked_items[item_id]
						item.stock += previous.get(item_id, 0) - desired.get(item_id, 0)
						item.save(update_fields=['stock'])

					for line_form in formset.forms:
						data = getattr(line_form, 'cleaned_data', {})
						if not data:
							continue
						if data.get('DELETE'):
							if line_form.instance.pk:
								line_form.instance.delete()
							continue
						item = locked_items[data['item'].pk]
						line = line_form.save(commit=False)
						line.purchase = purchase
						if not line.pk or line.item_id != line_form.initial.get('item'):
							line.unit_price = item.unit_price
						elif line.pk:
							line.unit_price = next(
								original.unit_price for original in original_lines if original.pk == line.pk
							)
						line.save()
					messages.success(request, f'{purchase.order_number} updated and stock reconciled.')
					return redirect('purchase_detail', pk=purchase.pk)
			else:
				error = None

		return render(request, 'myapp/purchase_form.html', {
			'form': form, 'formset': formset, 'title': f'Edit purchase #{pk}', 'stock_error': error,
		})

	purchase = get_object_or_404(Purchase, pk=pk)
	form, formset = _purchase_forms(request, purchase)
	return render(request, 'myapp/purchase_form.html', {
		'form': form, 'formset': formset, 'title': f'Edit purchase #{pk}',
	})


def _stock_error(desired, locked_items, previous=None):
	previous = previous or {}
	for item_id, quantity in desired.items():
		item = locked_items.get(item_id)
		if item is None:
			return 'One of the selected items is no longer available.'
		if not item.is_active and quantity > previous.get(item_id, 0):
			return f'{item.name} is inactive; its quantity cannot be increased.'
		available = item.stock + previous.get(item_id, 0)
		if quantity > available:
			return f'Not enough stock for {item.name}. Available: {available}; requested: {quantity}.'
	return None
