-- Usability test schema. Mirrors patterns in the real bastion-host DB:
--   * integer surrogate PK (users.id)
--   * prefix+number string PK (orders.order_code like "ORD0000001")
--   * composite PK (order_items)
--   * FK between tables
--   * JSON column (users.profile)
--   * A "remark" marker column that the tool auto-detects
--   * Unique key separate from PK (users.username)
-- Seed with ~5-10 rows per table so select_top_rows has material.

CREATE TABLE users (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(64) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL,
    profile JSON,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    remark VARCHAR(255),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE orders (
    order_code VARCHAR(32) PRIMARY KEY,
    user_id BIGINT NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    currency CHAR(3) NOT NULL DEFAULT 'JPY',
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    remark VARCHAR(255),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user (user_id),
    CONSTRAINT fk_orders_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE order_items (
    order_code VARCHAR(32) NOT NULL,
    line_no INT NOT NULL,
    sku VARCHAR(64) NOT NULL,
    qty INT NOT NULL,
    unit_price DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (order_code, line_no),
    CONSTRAINT fk_items_order FOREIGN KEY (order_code) REFERENCES orders(order_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO users (username, email, profile, status, remark) VALUES
  ('alice',  'alice@example.com',  '{"age":30,"locale":"en-US"}', 'active',    'seed'),
  ('bob',    'bob@example.com',    '{"age":25,"locale":"ja-JP"}', 'active',    'seed'),
  ('carol',  'carol@example.com',  '{"age":28,"locale":"zh-CN"}', 'suspended', 'seed'),
  ('dave',   'dave@example.com',   '{"age":42,"locale":"en-GB"}', 'active',    'seed'),
  ('eve',    'eve@example.com',    '{"age":35,"locale":"fr-FR"}', 'active',    'seed');

INSERT INTO orders (order_code, user_id, amount, currency, status, remark) VALUES
  ('ORD0000001', 1, 1500.00, 'JPY', 'paid',    'seed'),
  ('ORD0000002', 1,  800.50, 'JPY', 'pending', 'seed'),
  ('ORD0000003', 2, 2200.00, 'JPY', 'paid',    'seed'),
  ('ORD0000004', 3, 9999.99, 'JPY', 'refunded','seed'),
  ('ORD0000005', 4,  100.00, 'USD', 'paid',    'seed');

INSERT INTO order_items (order_code, line_no, sku, qty, unit_price) VALUES
  ('ORD0000001', 1, 'SKU-A', 2, 500.00),
  ('ORD0000001', 2, 'SKU-B', 1, 500.00),
  ('ORD0000002', 1, 'SKU-C', 1, 800.50),
  ('ORD0000003', 1, 'SKU-A', 4, 550.00),
  ('ORD0000004', 1, 'SKU-D', 1, 9999.99),
  ('ORD0000005', 1, 'SKU-E', 1, 100.00);

-- Give the mdf user permission to LOAD DATA LOCAL on this DB
GRANT ALL PRIVILEGES ON mdf_test.* TO 'mdf'@'%';
FLUSH PRIVILEGES;
