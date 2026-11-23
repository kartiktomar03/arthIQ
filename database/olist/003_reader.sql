-- A fresh LOGIN has no password until provisioned locally by the DBA.
CREATE ROLE arthiq_olist_analytics LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
COMMENT ON ROLE arthiq_olist_analytics IS 'ArthIQ Olist standalone reader v1';
REVOKE CREATE,TEMPORARY ON DATABASE arthiq_olist FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA olist FROM PUBLIC;
GRANT CONNECT ON DATABASE arthiq_olist TO arthiq_olist_analytics;
GRANT USAGE ON SCHEMA olist TO arthiq_olist_analytics;
GRANT SELECT ON olist.customers,olist.orders,olist.order_items,olist.order_payments,olist.order_reviews,
 olist.products,olist.sellers,olist.geolocation,olist.product_category_name_translation TO arthiq_olist_analytics;
ALTER ROLE arthiq_olist_analytics IN DATABASE arthiq_olist SET default_transaction_read_only = on;
