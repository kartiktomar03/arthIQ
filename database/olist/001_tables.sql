-- Executed transactionally by import_olist.py, after target and collision checks.
CREATE SCHEMA olist;
COMMENT ON SCHEMA olist IS 'ArthIQ Olist standalone import v1';
CREATE TABLE olist.customers (
 customer_id text PRIMARY KEY, customer_unique_id text NOT NULL, customer_zip_code_prefix text NOT NULL,
 customer_city text NOT NULL, customer_state text NOT NULL
);
CREATE TABLE olist.orders (
 order_id text PRIMARY KEY, customer_id text NOT NULL, order_status text NOT NULL,
 order_purchase_timestamp timestamp NOT NULL, order_approved_at timestamp, order_delivered_carrier_date timestamp,
 order_delivered_customer_date timestamp, order_estimated_delivery_date timestamp NOT NULL
);
CREATE TABLE olist.order_items (
 order_id text, order_item_id integer, product_id text NOT NULL, seller_id text NOT NULL,
 shipping_limit_date timestamp NOT NULL, price numeric NOT NULL, freight_value numeric NOT NULL,
 PRIMARY KEY(order_id,order_item_id)
);
CREATE TABLE olist.order_payments (
 order_id text, payment_sequential integer, payment_type text NOT NULL, payment_installments integer NOT NULL,
 payment_value numeric NOT NULL, PRIMARY KEY(order_id,payment_sequential)
);
CREATE TABLE olist.order_reviews (
 review_id text, order_id text, review_score integer NOT NULL, review_comment_title text, review_comment_message text,
 review_creation_date timestamp NOT NULL, review_answer_timestamp timestamp NOT NULL, PRIMARY KEY(review_id,order_id)
);
CREATE TABLE olist.products (
 product_id text PRIMARY KEY, product_category_name text, product_name_lenght integer,
 product_description_lenght integer, product_photos_qty integer, product_weight_g integer,
 product_length_cm integer, product_height_cm integer, product_width_cm integer
);
CREATE TABLE olist.sellers (
 seller_id text PRIMARY KEY, seller_zip_code_prefix text NOT NULL, seller_city text NOT NULL, seller_state text NOT NULL
);
CREATE TABLE olist.geolocation (
 geolocation_zip_code_prefix text NOT NULL, geolocation_lat numeric NOT NULL, geolocation_lng numeric NOT NULL,
 geolocation_city text NOT NULL, geolocation_state text NOT NULL
);
CREATE TABLE olist.product_category_name_translation (
 product_category_name text PRIMARY KEY, product_category_name_english text NOT NULL
);
