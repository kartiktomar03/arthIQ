# Olist import with pgAdmin 4 and PostgreSQL 19

Use a dedicated, empty local PostgreSQL 19 database named `arthiq_olist`. If the dataset is already imported, skip directly to the verification instructions in the project README.

## Import from a local folder

Obtain and extract the [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) separately. Follow its license terms. From the project root, point both commands at the folder containing the nine CSVs.

```powershell
$csv = Read-Host "Absolute path to extracted Olist CSV folder"
.\.venv\Scripts\python.exe database/olist/prepare_import.py "$csv"
if ($LASTEXITCODE -ne 0) { throw "CSV profiling failed" }
.\database\olist\Import-Olist.ps1 -CsvDirectory "$csv"
```

The first command profiles the local files and generates both SQL drivers and source-report.json. The second validates the nine paths, normalizes BOM-prefixed headers in temporary files and calls psql using its hidden password prompt. Both drivers contain local file paths and are excluded from Git. The setup role needs permission to create the schema and dedicated reader. For this extract use the PowerShell launcher so BOM handling runs before COPY.

## Scope and reruns

- First run creates exactly nine tables, eight primary keys, six foreign keys and nine additional indexes. Identifiers, cities, states and ZIP prefixes are text. Leading zeros survive. Timestamps have no invented time zone. Prices, freight, payment values and coordinates are PostgreSQL NUMERIC, without scale truncation. Integer quantities and ratings use integer. Column names and order match the files, including the source spellings `product_name_lenght` and `product_description_lenght`.
- COPY validates UTF-8, exact column headers and typed values. Quoted/multiline CSV text is parsed as a logical record. Empty fields, quoted or unquoted, become NULL. No ON_ERROR IGNORE, source updates, deduplication or inserts into the demo shop.
- On rerun, fresh temporary staging tables receive the CSVs. An EXCEPT ALL comparison in **both directions** verifies the installed typed rows including duplicate multiplicity. Differences abort. Existing business rows are never truncated or replaced. An advisory lock excludes concurrent import drivers. Allow disk space for staged data, indexes, WAL and temporary sorts. The source profiler uses temporary disk-backed SQLite and streaming reads.
- The fixed reader login `arthiq_olist_analytics` receives CONNECT, schema USAGE and SELECT on the nine named tables only. Effective permissions and reference totals are checked after SET LOCAL ROLE. It is not a table/schema owner and has no role memberships. The script revokes PUBLIC CREATE/TEMP in **arthiq_olist**, and PUBLIC CREATE on its public schema, to close inherited creation rights. It does not alter privileges in other databases. This import assumes a dedicated validation database. No application datasource configuration is changed.
- The newly created role has no password by default. If direct password-based login is needed later, use the pgAdmin **Login/Group Roles → arthiq_olist_analytics → Properties → Definition** password field locally. The role permissions and SET ROLE checks work without configuring a password.

## Independent reference values for this extract

| Measure | Expected |
|---|---:|
| Orders (one per order_id) | 99,441 |
| Delivered orders (order_status = delivered) | 96,478 |
| Distinct customers (customer_unique_id) | 96,096 |
| Order item lines | 112,650 |
| Delivered merchandise item price in BRL | 13,221,498.11 |
| Distinct sellers in sellers | 3,095 |

Delivered merchandise value is SUM(order_items.price) joined only to delivered orders on the verified unique order_id. Each item line contributes once. Freight, installments and payments are excluded. Review and payment joins would risk multiplying a line's value.

## Source anomalies intentionally preserved

- Geolocation contains 1,000,163 rows, 19,015 distinct ZIP prefixes and 261,831 excess identical CSV rows. No geolocation PK or unique ZIP index.
- Duplicate-key excess means rows beyond the first row per key. Reviews have 814 excess review IDs and 551 excess order IDs, but zero duplicate (review_id, order_id) pairs. Payments have 4,446 excess order IDs but zero duplicate (order_id, payment_sequential) pairs. Items have 13,984 excess order IDs and zero duplicate (order_id, order_item_id) pairs.
- Six enforced child → parent relationships have zero source orphans. There are 13 product rows with a non-null category missing from translations, and 278 customer rows and 7 seller rows with no matching geolocation ZIP. Those three lookups have no FK.
- 160 approval timestamps, 1,783 carrier-delivery timestamps and 2,965 customer-delivery timestamps are null. 87,656 reviews lack titles; 58,247 lack messages. 610 products lack a category, name length, description length and photo count; two lack each physical measure. Full counts for every column are in source-report.json.

