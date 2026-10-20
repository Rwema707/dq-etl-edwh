Test fixtures in the exact layout of the public Olist dataset.

* `olist_order_payments_dataset.csv`: real rows copied from the public file (including its mixed quoting
  and a genuine two-payment order, `683bf306...`).
* `olist_orders_dataset.csv`, `olist_customers_dataset.csv`: Olist's column layout, but the rows are stand-ins
  keyed to the real order ids above. The full real files are not committed; use `python -m sources.fetch_olist`.
