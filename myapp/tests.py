from decimal import Decimal

from django.test import TestCase
from django.db.models.deletion import ProtectedError
from django.urls import reverse

from .models import Item, ItemType, Purchase, PurchaseItem


class PurchaseWorkflowTests(TestCase):
	def setUp(self):
		self.item_type = ItemType.objects.create(name='Office supplies')
		self.pen = Item.objects.create(
			item_type=self.item_type,
			name='Pen',
			sku='PEN-01',
			unit_price='1.50',
			stock=12,
		)
		self.paper = Item.objects.create(
			item_type=self.item_type,
			name='Paper',
			sku='PAPER-01',
			unit_price='4.00',
			stock=8,
		)

	def purchase_data(self, lines, customer='Acme'):
		data = {
			'customer_name': customer,
			'lines-TOTAL_FORMS': str(len(lines)),
			'lines-INITIAL_FORMS': '0',
			'lines-MIN_NUM_FORMS': '1',
			'lines-MAX_NUM_FORMS': '1000',
		}
		for index, (item, quantity) in enumerate(lines):
			data[f'lines-{index}-item'] = str(item.pk)
			data[f'lines-{index}-quantity'] = str(quantity)
		return data

	def test_purchase_with_multiple_items_decrements_stock(self):
		response = self.client.post(
			reverse('purchase_create'),
			self.purchase_data([(self.pen, 3), (self.paper, 2)]),
		)

		self.assertRedirects(response, reverse('purchase_list'))
		self.pen.refresh_from_db()
		self.paper.refresh_from_db()
		purchase = Purchase.objects.get()
		self.assertEqual((self.pen.stock, self.paper.stock), (9, 6))
		self.assertEqual(purchase.lines.count(), 2)
		self.assertEqual(purchase.total, Decimal('12.50'))

	def test_insufficient_stock_rejects_entire_purchase(self):
		response = self.client.post(
			reverse('purchase_create'),
			self.purchase_data([(self.pen, 4), (self.paper, 9)]),
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Not enough stock for Paper')
		self.assertFalse(Purchase.objects.exists())
		self.pen.refresh_from_db()
		self.paper.refresh_from_db()
		self.assertEqual((self.pen.stock, self.paper.stock), (12, 8))

	def test_edit_adjusts_stock_and_keeps_original_unit_price(self):
		purchase = Purchase.objects.create(customer_name='Acme')
		line = PurchaseItem.objects.create(
			purchase=purchase, item=self.pen, quantity=3, unit_price='1.50'
		)
		self.pen.stock -= 3
		self.pen.save(update_fields=['stock'])
		self.pen.unit_price = '2.00'
		self.pen.save(update_fields=['unit_price'])
		data = {
			'customer_name': 'Acme revised',
			'lines-TOTAL_FORMS': '2',
			'lines-INITIAL_FORMS': '1',
			'lines-MIN_NUM_FORMS': '1',
			'lines-MAX_NUM_FORMS': '1000',
			'lines-0-id': str(line.pk),
			'lines-0-item': str(self.pen.pk),
			'lines-0-quantity': '5',
			'lines-1-item': '',
			'lines-1-quantity': '',
		}

		response = self.client.post(reverse('purchase_update', args=[purchase.pk]), data)

		self.assertRedirects(response, reverse('purchase_list'))
		self.pen.refresh_from_db()
		line.refresh_from_db()
		self.assertEqual(self.pen.stock, 7)
		self.assertEqual(line.quantity, 5)
		self.assertEqual(line.unit_price, Decimal('1.50'))

	def test_purchase_cannot_be_deleted(self):
		purchase = Purchase.objects.create()

		with self.assertRaises(ProtectedError):
			purchase.delete()
		with self.assertRaises(ProtectedError):
			Purchase.objects.filter(pk=purchase.pk).delete()

		self.assertTrue(Purchase.objects.filter(pk=purchase.pk).exists())

	def test_purchase_delete_route_is_not_exposed(self):
		response = self.client.get('/purchases/1/delete/')
		self.assertEqual(response.status_code, 404)

	def test_main_pages_render(self):
		purchase = Purchase.objects.create(customer_name='Acme')
		PurchaseItem.objects.create(purchase=purchase, item=self.pen, quantity=1, unit_price='1.50')
		dashboard_response = self.client.get(reverse('dashboard'))
		self.assertContains(dashboard_response, 'Active items')
		self.assertNotContains(dashboard_response, '{{ active_item_count }}')
		paths = [
			reverse('dashboard'),
			reverse('item_list'),
			reverse('item_type_list'),
			reverse('purchase_list'),
			reverse('item_create'),
			reverse('item_type_create'),
			reverse('purchase_create'),
			reverse('purchase_update', args=[purchase.pk]),
		]
		for path in paths:
			with self.subTest(path=path):
				self.assertEqual(self.client.get(path).status_code, 200)
