BEGIN;
CREATE TABLE IF NOT EXISTS shop.categories (
    id integer PRIMARY KEY,
    name varchar(60) NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS shop.customers (
    id integer PRIMARY KEY,
    name varchar(80) NOT NULL,
    region varchar(40) NOT NULL,
    joined_on date NOT NULL
);
CREATE TABLE IF NOT EXISTS shop.products (
    id integer PRIMARY KEY,
    category_id integer NOT NULL REFERENCES shop.categories(id),
    name varchar(80) NOT NULL UNIQUE,
    list_price numeric(10, 2) NOT NULL CHECK (list_price > 0)
);
CREATE TABLE IF NOT EXISTS shop.orders (
    id integer PRIMARY KEY,
    customer_id integer NOT NULL REFERENCES shop.customers(id),
    placed_on date NOT NULL,
    status varchar(12) NOT NULL CHECK (status IN ('completed', 'pending', 'cancelled'))
);
CREATE TABLE IF NOT EXISTS shop.order_items (
    order_id integer NOT NULL REFERENCES shop.orders(id),
    product_id integer NOT NULL REFERENCES shop.products(id),
    quantity integer NOT NULL CHECK (quantity > 0),
    unit_price numeric(10, 2) NOT NULL CHECK (unit_price > 0),
    PRIMARY KEY (order_id, product_id)
);

CREATE INDEX IF NOT EXISTS products_category_idx ON shop.products(category_id);
CREATE INDEX IF NOT EXISTS orders_customer_idx ON shop.orders(customer_id);
CREATE INDEX IF NOT EXISTS orders_placed_on_idx ON shop.orders(placed_on);
CREATE INDEX IF NOT EXISTS order_items_product_idx ON shop.order_items(product_id);

GRANT SELECT ON shop.categories, shop.customers, shop.products, shop.orders, shop.order_items
TO querypilot_analytics;
COMMIT;
