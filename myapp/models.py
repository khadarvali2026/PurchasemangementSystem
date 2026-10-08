from django.db import models
from django.db.models import Q
from django.db.models.deletion import ProtectedError


class PurchaseQuerySet(models.QuerySet):
	def delete(self):
		raise ProtectedError('Purchases cannot be deleted.', self)


class ItemType(models.Model):
	name = models.CharField(max_length=100, unique=True)
	description = models.TextField(blank=True)

	class Meta:
		db_table = 'item_types'
		ordering = ['name']

	def __str__(self):
		return self.name


class Item(models.Model):
	item_type = models.ForeignKey(ItemType, on_delete=models.PROTECT, related_name='items')
	name = models.CharField(max_length=150)
	sku = models.CharField(max_length=50, unique=True)
	description = models.TextField(blank=True)
	unit_price = models.DecimalField(max_digits=10, decimal_places=2)
	stock = models.PositiveIntegerField(default=0)
	is_active = models.BooleanField(default=True)

	class Meta:
		db_table = 'items'
		ordering = ['name']
		constraints = [
			models.CheckConstraint(condition=Q(unit_price__gte=0), name='item_price_nonnegative'),
			models.CheckConstraint(condition=Q(stock__gte=0), name='item_stock_nonnegative'),
		]

	def __str__(self):
		return f'{self.name} ({self.sku})'


class Purchase(models.Model):
	objects = PurchaseQuerySet.as_manager()

	customer_name = models.CharField(max_length=150, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		db_table = 'purchases'
		ordering = ['-created_at']

	def __str__(self):
		return f'Purchase #{self.pk}'

	@property
	def total(self):
		return sum((line.line_total for line in self.lines.all()), start=0)

	def delete(self, *args, **kwargs):
		raise ProtectedError('Purchases cannot be deleted.', self)


class PurchaseItem(models.Model):
	purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name='lines')
	item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name='purchase_lines')
	quantity = models.PositiveIntegerField()
	unit_price = models.DecimalField(max_digits=10, decimal_places=2)

	class Meta:
		db_table = 'purchase_items'
		constraints = [
			models.CheckConstraint(condition=Q(quantity__gt=0), name='purchase_item_quantity_positive'),
			models.CheckConstraint(condition=Q(unit_price__gte=0), name='purchase_item_price_nonnegative'),
		]

	def __str__(self):
		return f'{self.quantity} x {self.item.name}'

	@property
	def line_total(self):
		return self.quantity * self.unit_price
