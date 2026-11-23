-- Distinct customers = unique people/identities across the customers file.
-- Delivered merchandise value: sum each delivered line's price once; exclude freight/payments.
SELECT
 (SELECT count(*) FROM olist.orders) AS orders,
 (SELECT count(*) FROM olist.orders WHERE order_status='delivered') AS delivered_orders,
 (SELECT count(DISTINCT customer_unique_id) FROM olist.customers) AS distinct_customers,
 (SELECT count(*) FROM olist.order_items) AS order_items,
 (SELECT sum(i.price)::text FROM olist.order_items i JOIN olist.orders o USING(order_id)
   WHERE o.order_status='delivered') AS delivered_item_price_brl,
 (SELECT count(DISTINCT seller_id) FROM olist.sellers) AS unique_sellers;
