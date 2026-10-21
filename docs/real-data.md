# Using real public data (Olist)

The simulator is ideal for demonstrating failures on demand. For a credible proposal, the pipeline can also
run on **real data**: the public *Brazilian E-Commerce Dataset by Olist* (about 99k real orders, 2016-2018,
published on Kaggle). It is replayed as daily batches: each purchase date becomes one batch file, so real weekly
patterns, a real Black Friday spike and real data defects flow through the same checks.

## What it demonstrates that the simulator cannot
- **Weekday seasonality** is real, which is why the volume check compares Mondays with Mondays.
- **Genuine defects.** The source is not guaranteed clean. Orders without a payment record or customer lookup
  keep their empty amount/customer, so the `required_fields_not_null` check blocks that day. Nothing is cleaned
  or dropped upstream (that would hide exactly what the pipeline exists to catch).
- **Real spikes** (e.g. Black Friday 2017) trip the volume check; the hint explains it may be genuine.

## Mapping to the `orders` contract (`contracts/olist_orders.yaml`)
| Contract column | Olist source |
|---|---|
| `order_id` | `orders.order_id` |
| `customer_id` | `customers.customer_unique_id` (the real person; Olist's `customer_id` is per order) |
| `amount` | sum of `order_payments.payment_value` per order (BRL) |
| `status` | `orders.order_status` (8 known states) |
| `order_ts` | `orders.order_purchase_timestamp` |

`email` does not exist in Olist (data is anonymised), so this contract omits it.

## Run it locally
```bash
pip install -r requirements-etl.txt
python -m sources.fetch_olist                    # downloads 3 files to data/raw/olist, verifies row counts
python -m sources.olist --start 2018-03-01 --end 2018-04-15      # writes data/incoming/orders_<date>.csv
python -m etl.backfill --contract contracts/olist_orders.yaml --db data/olist.db \
       --start 2018-03-01 --end 2018-04-15      # replays oldest to newest; prints blocked days
DQ_DB_PATH=data/olist.db uvicorn api.app:app --port 8000     # dashboard on the real data (or point it at any shared database)
```
`fetch_olist` uses a community Hugging Face mirror by default (third-party, may move). Alternatives:
`--kaggle` (needs `pip install kagglehub`, possibly Kaggle credentials) or `--base-url` for your own copy. Wrong
or truncated downloads are rejected by row count (99,441 orders, 99,441 customers, 103,886 payments).

## Run it in GitHub Actions into your cloud database
**Actions -> Load Olist demo data -> Run workflow** (choose a start/end date). It uses the `DATABASE_URL` secret.

> **Datasets can share one database.** Runs and loaded rows carry a `dataset` column, the volume baseline only
> looks at the same dataset's history, and reloading one dataset never touches another's rows. The dashboard has a
> **Dataset** picker (shown when more than one exists; `?dataset=olist_orders` in the URL opens one directly).
> Without a choice, it shows the dataset that ran most recently.

## Declaring expected spikes (`known_events`)
A real spike such as Black Friday is not an incident, so the volume check lets a contract declare it:
```yaml
known_events:
  - date: "2017-11-24"
    note: Black Friday
    factor: [1.5, 8.0]     # on that date the batch must be 1.5x to 8x the usual volume
```
On that date the normal +/-35% band is replaced by the declared range, so a *missing* spike (a half-loaded
Black Friday) is still caught. The shipped range is deliberately generous: replay November 2017 once and tighten it.

## Good date ranges
| Range | What you get |
|---|---|
| 2018-03-01 to 2018-04-15 | The steadiest part of the data; mostly green with occasional real findings |
| 2017-11-01 to 2017-12-15 | Includes Black Friday (2017-11-24): a real volume spike |
| 2016-09 to 2017-01 | Very sparse early data: volume and freshness checks will legitimately complain |

## Caveats
- Timestamps are Brazilian local time; the contract treats them as UTC (an error of up to 3 hours, irrelevant for
  daily batches, noted for honesty).
- The first 3 same-weekday batches have no baseline; the volume check reports SKIPPED rather than passing.
- The dataset's licence (Kaggle lists it as CC BY-NC-SA 4.0; verify before reuse) restricts commercial use and
  redistribution. Fine for an internal proposal demo; do not commit the CSVs (`data/` is gitignored).
- `tests/fixtures/olist/` holds a few real payment rows plus Olist-layout stand-ins for orders and customers.
