"""Stream Olist CSVs; use a disposable on-disk SQLite index for source-only checks."""
import csv
import hashlib
import json
import sqlite3
import tempfile
from contextlib import closing
from collections import Counter
from decimal import Decimal
from pathlib import Path

COLUMNS = {
    "customers": "customer_id customer_unique_id customer_zip_code_prefix customer_city customer_state",
    "orders": "order_id customer_id order_status order_purchase_timestamp order_approved_at order_delivered_carrier_date order_delivered_customer_date order_estimated_delivery_date",
    "order_items": "order_id order_item_id product_id seller_id shipping_limit_date price freight_value",
    "order_payments": "order_id payment_sequential payment_type payment_installments payment_value",
    "order_reviews": "review_id order_id review_score review_comment_title review_comment_message review_creation_date review_answer_timestamp",
    "products": "product_id product_category_name product_name_lenght product_description_lenght product_photos_qty product_weight_g product_length_cm product_height_cm product_width_cm",
    "sellers": "seller_id seller_zip_code_prefix seller_city seller_state",
    "geolocation": "geolocation_zip_code_prefix geolocation_lat geolocation_lng geolocation_city geolocation_state",
    "product_category_name_translation": "product_category_name product_category_name_english",
}
KEYS = {"customers":"customer_id", "orders":"order_id", "order_items":"order_id,order_item_id",
        "order_payments":"order_id,payment_sequential", "order_reviews":"review_id,order_id",
        "products":"product_id", "sellers":"seller_id", "product_category_name_translation":"product_category_name"}
FOREIGN_KEYS = [
    ("orders","customer_id","customers","customer_id"),
    ("order_items","order_id","orders","order_id"),
    ("order_items","product_id","products","product_id"),
    ("order_items","seller_id","sellers","seller_id"),
    ("order_payments","order_id","orders","order_id"),
    ("order_reviews","order_id","orders","order_id"),
]
LINKS = FOREIGN_KEYS + [
    ("products","product_category_name","product_category_name_translation","product_category_name"),
    ("customers","customer_zip_code_prefix","geolocation","geolocation_zip_code_prefix"),
    ("sellers","seller_zip_code_prefix","geolocation","geolocation_zip_code_prefix"),
]
def filename(t):
    return ("olist_"+t+"_dataset" if t!="product_category_name_translation" else t)+".csv"

def orphan_sql(link, prefix):
    t,col,parent,pk=link
    return (f"SELECT count(*) FROM {prefix}{t} c WHERE c.{col} IS NOT NULL AND NOT EXISTS "
            f"(SELECT 1 FROM {prefix}{parent} p WHERE p.{pk}=c.{col})")

def profile(folder):
    stats={}
    with tempfile.TemporaryDirectory() as tmp, closing(sqlite3.connect(Path(tmp)/"profile.sqlite")) as db:
        db.execute("PRAGMA temp_store=FILE")
        for table,names in COLUMNS.items():
            cols=names.split()
            path=folder/filename(table)
            digest=hashlib.sha256()
            with path.open("rb") as f:
                for chunk in iter(lambda:f.read(1024*1024),b""):digest.update(chunk)
            db.execute(f"CREATE TABLE {table} ({','.join(c+' TEXT' for c in cols)})")
            nulls=Counter(dict.fromkeys(cols,0))
            n=0
            with path.open(encoding="utf-8-sig",newline="") as f:
                reader=csv.reader(f,strict=True)
                if next(reader,None)!=cols:raise ValueError(f"{path.name}: unexpected CSV header")
                def rows():
                    nonlocal n
                    for row in reader:
                        if len(row)!=len(cols):raise ValueError(f"{path.name}: wrong field count near line {reader.line_num}")
                        n+=1
                        nulls.update(c for c,v in zip(cols,row) if not v)
                        yield [v or None for v in row]
                db.executemany(f"INSERT INTO {table} VALUES ({','.join('?' for _ in cols)})",rows())
            def excess(key):
                return db.execute(f"SELECT coalesce(sum(n-1),0) FROM (SELECT count(*) n FROM {table} GROUP BY {key} HAVING count(*)>1)").fetchone()[0]
            candidates=[KEYS[table]] if table in KEYS else []
            if table in ("order_reviews","order_items","order_payments"):candidates+=["order_id"]
            if table=="order_reviews":candidates+=["review_id"]
            if table=="customers":candidates+=["customer_unique_id"]
            if table=="geolocation":candidates+=["geolocation_zip_code_prefix"]
            stats[table]=dict(rows=n,sha256=digest.hexdigest(),nulls=dict(nulls),duplicate_key_excess={k:excess(k) for k in candidates},identical_row_excess=excess(','.join(cols)))
        for table,col in sorted({(p,k) for _,_,p,k in LINKS} | {("orders","order_id")}):
            db.execute(f"CREATE INDEX lookup_{table}_{col} ON {table}({col})")
        orphans={'.'.join((t,c))+' -> '+p+'.'+k:db.execute(orphan_sql((t,c,p,k),'')).fetchone()[0] for t,c,p,k in LINKS}
        count=lambda q:db.execute(q).fetchone()[0]
        total=sum((Decimal(row[0]) for row in db.execute("SELECT i.price FROM order_items i JOIN orders o USING(order_id) WHERE o.order_status='delivered'")),Decimal(0))
        refs=dict(orders=stats["orders"]["rows"],delivered_orders=count("SELECT count(*) FROM orders WHERE order_status='delivered'"),
                  distinct_customers=count("SELECT count(DISTINCT customer_unique_id) FROM customers"),order_items=stats["order_items"]["rows"],
                  delivered_item_price_brl=str(total),unique_sellers=count("SELECT count(DISTINCT seller_id) FROM sellers"))
        return dict(tables=stats,orphan_rows=orphans,source_reference=refs)


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("csv_dir",type=Path);p.add_argument("output",type=Path);a=p.parse_args()
    a.output.write_text(json.dumps(profile(a.csv_dir),indent=2)+"\n",encoding="utf8")

