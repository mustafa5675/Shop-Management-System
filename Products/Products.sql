USE shop_management;

CREATE TABLE IF NOT EXISTS `Products` (
    product_id INT AUTO_INCREMENT PRIMARY KEY,
    product_name VARCHAR(100) NOT NULL,
    buying_price DECIMAL(20,0),
    selling_price DECIMAL(20,0),
    is_expirable BOOLEAN NOT NULL DEFAULT FALSE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
);

-- Audit table for Products
CREATE TABLE IF NOT EXISTS Products_audit (
    audit_id INT AUTO_INCREMENT PRIMARY KEY,
    product_id INT,
    action ENUM('INSERT', 'UPDATE', 'DELETE') NOT NULL,
    action_by VARCHAR(100) NOT NULL,
    action_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    product_name VARCHAR(100),
    is_expirable BOOLEAN
);


CREATE TABLE IF NOT EXISTS `Inventory_lots` (
    lot_id INT AUTO_INCREMENT PRIMARY KEY,
    product_id INT NOT NULL,
    quantity INT NOT NULL,
    expiry_date DATE DEFAULT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,

    FOREIGN KEY (product_id) REFERENCES products(product_id)
);

-- Audit table for Inventory_lots
CREATE TABLE IF NOT EXISTS Inventory_lots_audit (
    audit_id INT AUTO_INCREMENT PRIMARY KEY,
    lot_id INT,
    product_id INT,
    action ENUM('INSERT', 'UPDATE', 'DELETE') NOT NULL,
    action_by VARCHAR(100) NOT NULL,
    action_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    quantity INT,
    expiry_date DATE
);