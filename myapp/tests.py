from decimal import Decimal
from datetime import date

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

		purchase = Purchase.objects.get()
		self.assertRedirects(response, reverse('purchase_detail', args=[purchase.pk]))
		self.pen.refresh_from_db()
		self.paper.refresh_from_db()
		self.assertEqual((self.pen.stock, self.paper.stock), (9, 6))
		self.assertEqual(purchase.lines.count(), 2)
		self.assertEqual(purchase.total, Decimal('12.50'))
		self.assertEqual(purchase.order_number, f'PO-{purchase.pk:05d}')

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

	def test_zero_quantity_is_rejected_by_form_validation(self):
		response = self.client.post(
			reverse('purchase_create'),
			self.purchase_data([(self.pen, 0)]),
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Ensure this value is greater than or equal to 1')
		self.assertFalse(Purchase.objects.exists())
		self.pen.refresh_from_db()
		self.assertEqual(self.pen.stock, 12)

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

		self.assertRedirects(response, reverse('purchase_detail', args=[purchase.pk]))
		self.pen.refresh_from_db()
		line.refresh_from_db()
		self.assertEqual(self.pen.stock, 7)
		self.assertEqual(line.quantity, 5)
		self.assertEqual(line.unit_price, Decimal('1.50'))

	def test_item_purchase_date_can_be_created(self):
		form_response = self.client.get(reverse('item_create'))
		self.assertContains(form_response, 'Initial stock')
		response = self.client.post(reverse('item_create'), {
			'item_type': self.item_type.pk,
			'name': 'Notebook',
			'sku': 'NOTE-01',
			'purchase_date': '2026-08-25',
			'description': '',
			'unit_price': '3.00',
			'stock': '4',
			'is_active': 'on',
		})

		self.assertRedirects(response, reverse('item_list'))
		item = Item.objects.get(sku='NOTE-01')
		self.assertEqual(item.purchase_date, date(2026, 8, 25))
		self.assertContains(self.client.get(reverse('item_update', args=[item.pk])), 'Current stock')

	def test_item_used_in_history_cannot_be_deleted(self):
		purchase = Purchase.objects.create(customer_name='Acme')
		PurchaseItem.objects.create(
			purchase=purchase, item=self.pen, quantity=2, unit_price='1.50'
		)
		list_response = self.client.get(reverse('item_list'))
		self.assertContains(list_response, 'History')
		self.assertNotContains(list_response, reverse('item_delete', args=[self.pen.pk]))
		detail_response = self.client.get(reverse('item_detail', args=[self.pen.pk]))
		self.assertContains(detail_response, purchase.order_number)
		self.assertContains(detail_response, 'This item cannot be deleted while history exists.')

		response = self.client.post(reverse('item_delete', args=[self.pen.pk]))

		self.assertRedirects(response, reverse('item_detail', args=[self.pen.pk]))
		self.assertTrue(Item.objects.filter(pk=self.pen.pk).exists())

	def test_item_without_history_can_be_deleted(self):
		response = self.client.post(reverse('item_delete', args=[self.pen.pk]))

		self.assertRedirects(response, reverse('item_list'))
		self.assertFalse(Item.objects.filter(pk=self.pen.pk).exists())

	def test_inactive_item_quantity_cannot_be_increased_on_purchase_edit(self):
		purchase = Purchase.objects.create(customer_name='Acme')
		line = PurchaseItem.objects.create(
			purchase=purchase, item=self.pen, quantity=3, unit_price='1.50'
		)
		self.pen.stock -= 3
		self.pen.is_active = False
		self.pen.save(update_fields=['stock', 'is_active'])
		data = {
			'customer_name': 'Acme',
			'lines-TOTAL_FORMS': '1',
			'lines-INITIAL_FORMS': '1',
			'lines-MIN_NUM_FORMS': '1',
			'lines-MAX_NUM_FORMS': '1000',
			'lines-0-id': str(line.pk),
			'lines-0-item': str(self.pen.pk),
			'lines-0-quantity': '4',
		}

		response = self.client.post(reverse('purchase_update', args=[purchase.pk]), data)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'is inactive; its quantity cannot be increased')
		self.pen.refresh_from_db()
		line.refresh_from_db()
		self.assertEqual(self.pen.stock, 9)
		self.assertEqual(line.quantity, 3)

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
		detail_response = self.client.get(reverse('purchase_detail', args=[purchase.pk]))
		self.assertContains(detail_response, purchase.order_number)
		self.assertContains(detail_response, 'Purchase date:')
		self.assertContains(detail_response, 'Office supplies')
		self.assertContains(detail_response, 'Current stock')
		paths = [
			reverse('dashboard'),
			reverse('item_list'),
				reverse('item_detail', args=[self.pen.pk]),
			reverse('item_type_list'),
			reverse('purchase_list'),
			reverse('purchase_detail', args=[purchase.pk]),
			reverse('item_create'),
			reverse('item_type_create'),
			reverse('purchase_create'),
			reverse('purchase_update', args=[purchase.pk]),
		]
		for path in paths:
			with self.subTest(path=path):
				response = self.client.get(path)
				self.assertEqual(response.status_code, 200)
				self.assertNotContains(response, '{{')
				self.assertNotContains(response, '{%')
