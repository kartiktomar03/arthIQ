"""Deterministic expected rows for the untouched Phase 1 seed."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Case:
    question: str
    sql: str | None
    expected: tuple[tuple, ...] = ()
    tables: tuple[str, ...] = ()
    joins: tuple[tuple[str, str], ...] = ()
    ordered: bool = True


def case(question, sql, expected, tables, joins=(), ordered=True):
    return Case(question, sql, tuple(map(tuple, expected)), tuple(tables.split()), tuple(joins), ordered)


ITEM_ORDER = ("order_items", "orders")
ITEM_PRODUCT = ("order_items", "products")
PRODUCT_CATEGORY = ("products", "categories")
ORDER_CUSTOMER = ("orders", "customers")
REVENUE = "SUM(i.quantity * i.unit_price)"
ITEMS = "FROM order_items i JOIN orders o ON i.order_id = o.id"
COMPLETED = "WHERE o.status = 'completed'"
BY_PRODUCT = f"{ITEMS} JOIN products p ON i.product_id = p.id {COMPLETED}"
BY_CUSTOMER = f"{ITEMS} JOIN customers c ON o.customer_id = c.id {COMPLETED}"


CASES = (
    case("List the three category names alphabetically.", "SELECT name FROM categories ORDER BY name",
         [["Home Office"], ["Kitchen"], ["Outdoor"]], "categories"),
    case("How many products are in the catalog?", "SELECT COUNT(*) FROM products", [[6]], "products"),
    case("List all unique customer regions.", "SELECT DISTINCT region FROM customers ORDER BY region",
         [["East"], ["North"], ["South"], ["West"]], "customers", ordered=False),
    case("How many orders are there?", "SELECT COUNT(*) FROM orders", [[10]], "orders"),
    case("How many order items are there?", "SELECT COUNT(*) FROM order_items", [[18]], "order_items"),
    case("What is the highest list price among products?", "SELECT MAX(list_price) FROM products", [["60"]], "products"),
    case("What is the lowest unit price among line items?", "SELECT MIN(unit_price) FROM order_items", [["15"]], "order_items"),
    case("What is the average product list price?", "SELECT AVG(list_price) FROM products", [["34.1666666666666667"]], "products"),
    case("How many customers are in the East region?", "SELECT COUNT(*) FROM customers WHERE region = 'East'", [[2]], "customers"),
    case("Which product names have a list price below 25?", "SELECT name FROM products WHERE list_price < 25 ORDER BY name",
         [["Insulated Mug"], ["Trail Bottle"]], "products", ordered=False),
    case("How many completed orders are there?", "SELECT COUNT(*) FROM orders WHERE status = 'completed'", [[8]], "orders"),
    case("Which order IDs are pending?", "SELECT id FROM orders WHERE status = 'pending'", [[10]], "orders"),
    case("Which order IDs were cancelled?", "SELECT id FROM orders WHERE status = 'cancelled'", [[9]], "orders"),
    case("Count orders by status.", "SELECT status, COUNT(*) FROM orders GROUP BY status ORDER BY status",
         [["cancelled", 1], ["completed", 8], ["pending", 1]], "orders", ordered=False),
    case("How many orders were placed in January 2025?",
         "SELECT COUNT(*) FROM orders WHERE placed_on >= '2025-01-01' AND placed_on < '2025-02-01'", [[4]], "orders"),
    case("Count completed orders placed in February 2025.",
         "SELECT COUNT(*) FROM orders WHERE status = 'completed' AND placed_on >= '2025-02-01' AND placed_on < '2025-03-01'", [[4]], "orders"),
    case("How many customers joined before 2025?", "SELECT COUNT(*) FROM customers WHERE joined_on < '2025-01-01'",
         [[2]], "customers"),
    case("Which customers joined on or after 2025-02-01?",
         "SELECT name FROM customers WHERE joined_on >= '2025-02-01' ORDER BY name",
         [["Dev Patel"], ["Nina Roy"]], "customers", ordered=False),
    case("Count products in each category.",
         "SELECT c.name, COUNT(*) FROM categories c JOIN products p ON c.id = p.category_id GROUP BY c.name ORDER BY c.name",
         [["Home Office", 2], ["Kitchen", 2], ["Outdoor", 2]], "categories products", [PRODUCT_CATEGORY], ordered=False),
    case("Which products belong to the Kitchen category?",
         "SELECT p.name FROM products p JOIN categories c ON p.category_id = c.id WHERE c.name = 'Kitchen' ORDER BY p.name",
         [["Insulated Mug"], ["Pour-over Kit"]], "products categories", [PRODUCT_CATEGORY], ordered=False),
    case("List customers who have completed an order.",
         "SELECT DISTINCT c.name FROM customers c JOIN orders o ON c.id = o.customer_id WHERE o.status = 'completed' ORDER BY c.name",
         [["Asha Rao"], ["Dev Patel"], ["Kabir Sen"], ["Meera Das"], ["Nina Roy"], ["Ravi Shah"]],
         "customers orders", [ORDER_CUSTOMER], ordered=False),
    case("How many orders did customer Asha Rao place?",
         "SELECT COUNT(*) FROM orders o JOIN customers c ON o.customer_id = c.id WHERE c.name = 'Asha Rao'",
         [[2]], "orders customers", [ORDER_CUSTOMER]),
    case("Which products were never ordered?",
         "SELECT p.name FROM products p LEFT JOIN order_items i ON p.id = i.product_id WHERE i.product_id IS NULL",
         [], "products order_items", [ITEM_PRODUCT], ordered=False),
    case("Which products did Asha Rao buy? Match the customer by name.",
         "SELECT DISTINCT p.name FROM products p JOIN order_items i ON p.id = i.product_id "
         "JOIN orders o ON i.order_id = o.id JOIN customers c ON o.customer_id = c.id WHERE c.name = 'Asha Rao' ORDER BY p.name",
         [["Desk Lamp"], ["Insulated Mug"], ["Monitor Stand"]], "products order_items orders customers",
         [ITEM_PRODUCT, ITEM_ORDER, ORDER_CUSTOMER], ordered=False),
    case("What is total revenue?", f"SELECT {REVENUE} {ITEMS} {COMPLETED}", [["782"]], "orders order_items", [ITEM_ORDER]),
    case("Which are the top 5 products by total revenue?",
         f"SELECT p.name, {REVENUE} AS revenue {BY_PRODUCT} GROUP BY p.name ORDER BY revenue DESC, p.name LIMIT 5",
         [["Daypack", "175"], ["Monitor Stand", "175"], ["Desk Lamp", "140"], ["Pour-over Kit", "135"], ["Insulated Mug", "112"]],
         "orders order_items products", [ITEM_ORDER, ITEM_PRODUCT]),
    case("Show total revenue by category.",
         f"SELECT c.name, {REVENUE} {ITEMS} JOIN products p ON i.product_id = p.id "
         f"JOIN categories c ON p.category_id = c.id {COMPLETED} GROUP BY c.name ORDER BY c.name",
         [["Home Office", "315"], ["Kitchen", "247"], ["Outdoor", "220"]],
         "orders order_items products categories", [ITEM_ORDER, ITEM_PRODUCT, PRODUCT_CATEGORY], ordered=False),
    case("Which customers generated the highest revenue?",
         f"SELECT c.name, {REVENUE} AS revenue {BY_CUSTOMER} GROUP BY c.name ORDER BY revenue DESC, c.name LIMIT 1",
         [["Asha Rao", "185"]], "customers orders order_items", [ITEM_ORDER, ORDER_CUSTOMER]),
    case("What was total revenue from orders placed in February 2025?",
         f"SELECT {REVENUE} {ITEMS} {COMPLETED} AND o.placed_on >= '2025-02-01' AND o.placed_on < '2025-03-01'",
         [["347"]], "orders order_items", [ITEM_ORDER]),
    case("What was the total sales value in January 2025?",
         f"SELECT {REVENUE} {ITEMS} {COMPLETED} AND o.placed_on >= '2025-01-01' AND o.placed_on < '2025-02-01'",
         [["435"]], "orders order_items", [ITEM_ORDER]),
    case("What is the total turnover from pending orders?",
         f"SELECT {REVENUE} {ITEMS} {COMPLETED} AND o.status = 'pending'", [[None]], "orders order_items", [ITEM_ORDER]),
    case("What is the revenue for customers in the West region?",
         f"SELECT {REVENUE} {BY_CUSTOMER} AND c.region = 'West'", [["270"]],
         "customers orders order_items", [ITEM_ORDER, ORDER_CUSTOMER]),
    Case("What is today's weather?", None),
    Case("Explain the history of the Moon.", None),
    Case("What is the employee payroll total?", None),
    Case("Which are the best products?", None),
    Case("Show customer performance.", None),
    Case("Show me everything.", None),
    Case("What is the email address of every customer?", None),
    Case("Please remove the cancelled orders.", None),
)
