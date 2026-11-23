BEGIN;
-- Resets the five synthetic demo tables.
TRUNCATE shop.order_items, shop.orders, shop.products, shop.customers, shop.categories;

INSERT INTO shop.categories VALUES (1, 'Home Office'), (2, 'Kitchen'), (3, 'Outdoor');
INSERT INTO shop.customers VALUES
  (1, 'Asha Rao', 'West', '2024-12-10'), (2, 'Kabir Sen', 'East', '2024-12-13'),
  (3, 'Meera Das', 'South', '2025-01-04'), (4, 'Ravi Shah', 'North', '2025-01-12'),
  (5, 'Nina Roy', 'East', '2025-02-01'), (6, 'Dev Patel', 'West', '2025-02-05');

INSERT INTO shop.products VALUES
  (1, 1, 'Monitor Stand', 45), (2, 1, 'Desk Lamp', 30), (3, 2, 'Pour-over Kit', 35),
  (4, 2, 'Insulated Mug', 20), (5, 3, 'Daypack', 60), (6, 3, 'Trail Bottle', 15);

INSERT INTO shop.orders VALUES
  (1, 1, '2025-01-08', 'completed'), (2, 2, '2025-01-10', 'completed'),
  (3, 3, '2025-01-18', 'completed'), (4, 4, '2025-01-29', 'completed'),
  (5, 5, '2025-02-03', 'completed'), (6, 6, '2025-02-08', 'completed'),
  (7, 1, '2025-02-17', 'completed'), (8, 4, '2025-02-28', 'completed'),
  (9, 2, '2025-03-01', 'cancelled'), (10, 5, '2025-03-04', 'pending');

INSERT INTO shop.order_items VALUES
  (1, 1, 2, 45), (1, 2, 1, 30), (2, 3, 2, 35), (2, 4, 1, 20),
  (3, 5, 2, 60), (3, 6, 1, 15), (4, 2, 2, 25), (4, 1, 1, 40),
  (5, 4, 4, 18), (5, 3, 1, 30), (6, 5, 1, 55), (6, 6, 2, 15),
  (7, 1, 1, 45), (7, 4, 1, 20), (8, 2, 2, 30), (8, 3, 1, 35),
  (9, 6, 20, 15), (10, 2, 30, 30);
COMMIT;
