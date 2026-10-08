# PurchasemangementSystem

Django inventory and purchasing management application with item types, stock tracking, and purchase history.

## Setup

1. Create and activate a virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Create a MySQL database named `purchasemanagementsystem`.
4. Copy `.env.example` to `.env` and set the MySQL password and a private Django secret key.
5. Run `python manage.py migrate` and then `python manage.py runserver`.

The `.env` file contains local credentials and is excluded from Git.