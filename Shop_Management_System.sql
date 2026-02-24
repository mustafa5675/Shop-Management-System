USE shop_management;
CREATE TABLE IF NOT EXISTS `Sales` (
	`Sales_ID` int AUTO_INCREMENT NOT NULL UNIQUE,
	`Sales_Date` date NOT NULL,
	`Quan_Sold` int NOT NULL DEFAULT '1',
	`Unit_Price` decimal(10,2) NOT NULL,
	`Total` decimal(10,2) NOT NULL,
	`Payment_Method` enum NOT NULL,
	`Customer_ID` int NOT NULL,
	`Product_ID` int NOT NULL,
	PRIMARY KEY (`Sales_ID`)
);

CREATE TABLE IF NOT EXISTS `Customers` (
	`Customers_ID` int AUTO_INCREMENT NOT NULL UNIQUE,
	`Customer_Name` varchar(50) NOT NULL,
	`Phone_No.` decimal(15,0) NOT NULL UNIQUE,
	`Email` varchar(100) NOT NULL UNIQUE,
	`Address` varchar(100) NOT NULL,
	`CIty` varchar(50) NOT NULL,
	`Pincode` decimal(10,0) NOT NULL UNIQUE,
	`State` varchar(20) NOT NULL,
	`Country` varchar(20) NOT NULL,
	`Registr_Date` date NOT NULL,
	PRIMARY KEY (`Customers_ID`)
);

CREATE TABLE IF NOT EXISTS `Purchases` (
	`Purchase_ID` int AUTO_INCREMENT NOT NULL UNIQUE DEFAULT '1',
	`Products_ID` int NOT NULL,
	`Vendors_ID` int NOT NULL,
	`Quan_Purchased` int NOT NULL,
	`Unit_Cost` decimal(10,2) NOT NULL,
	`Total` decimal(10,2) NOT NULL,
	`Due_Date` date NOT NULL,
	`Payment-Status` enum NOT NULL DEFAULT ''credit'',
	PRIMARY KEY (`Purchase_ID`)
);

CREATE TABLE IF NOT EXISTS `Sales_Return` (
	`SalesR_ID` int AUTO_INCREMENT NOT NULL UNIQUE DEFAULT '1',
	`Sales_ID` int NOT NULL,
	`Customers_ID` int NOT NULL,
	`Products_ID` int NOT NULL,
	`SalesR_Date` date NOT NULL,
	`Quan_Returned` int NOT NULL,
	`Total` decimal(10,0) NOT NULL,
	`Reason` varchar(255) DEFAULT '255',
	`Status` enum NOT NULL DEFAULT '"pending"',
	PRIMARY KEY (`SalesR_ID`)
);

CREATE TABLE IF NOT EXISTS `Vendors` (
	`Vendors_ID` int AUTO_INCREMENT NOT NULL UNIQUE DEFAULT '1',
	`Name` varchar(80) NOT NULL,
	`Email` varchar(100) NOT NULL UNIQUE,
	`Phone_No.` decimal(15,0) NOT NULL UNIQUE,
	`Address` varchar(150) NOT NULL,
	`City` varchar(50) NOT NULL,
	`State` varchar(50) NOT NULL,
	`Postal_Code` decimal(10,0) NOT NULL,
	`Country` varchar(50) NOT NULL,
	`Credit_Period_Days` int NOT NULL,
	PRIMARY KEY (`Vendors_ID`)
);

CREATE TABLE IF NOT EXISTS `Pruchase_Return` (
	`PurchaseR_ID` int AUTO_INCREMENT NOT NULL UNIQUE,
	`Products_ID` int NOT NULL,
	`Purchase_ID` int NOT NULL,
	`Vendors_ID` int NOT NULL,
	`Return_Date` date NOT NULL,
	`Quan_Returned` int NOT NULL DEFAULT '1',
	`Total` decimal(10,2) NOT NULL,
	`Reason` varchar(255) NOT NULL,
	`Status` enum NOT NULL DEFAULT ''pending'',
	PRIMARY KEY (`PurchaseR_ID`)
);

CREATE TABLE IF NOT EXISTS `Products` (
    product_id INT AUTO_INCREMENT PRIMARY KEY,
    product_name VARCHAR(100) NOT NULL,
    is_expirable BOOLEAN NOT NULL DEFAULT FALSE,
	created_by VARCHAR(100) DEFAULT NULL,
	created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	updated_by VARCHAR(100) DEFAULT NULL,
	updated_at TIMESTAMP NULL DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
	deleted_by VARCHAR(100) DEFAULT NULL,
	deleted_at TIMESTAMP NULL DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS `Inventory_lots` (
    lot_id INT AUTO_INCREMENT PRIMARY KEY,
    product_id INT NOT NULL,
    quantity INT NOT NULL,
    expiry_date DATE DEFAULT NULL,
	created_by VARCHAR(100) DEFAULT NULL,
	created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
	updated_by VARCHAR(100) DEFAULT NULL,
	updated_at TIMESTAMP NULL DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
	deleted_by VARCHAR(100) DEFAULT NULL,
	deleted_at TIMESTAMP NULL DEFAULT NULL,
	FOREIGN KEY (product_id) REFERENCES products(product_id)
);


CREATE TABLE IF NOT EXISTS `Employees` (
	`Employee_ID` int AUTO_INCREMENT NOT NULL UNIQUE,
	`Name` varchar(100) NOT NULL,
	`Phone_No.` decimal(15,0) NOT NULL,
	`Email` varchar(255) NOT NULL,
	`City` varchar(50) NOT NULL,
	`State` varchar(20) NOT NULL,
	`Country` varchar(30) NOT NULL,
	`Adddress` varchar(1000) NOT NULL,
	`Hire_Date` date NOT NULL,
	`Salary` decimal(10,2) NOT NULL,
	PRIMARY KEY (`Employee_ID`)
);

CREATE TABLE IF NOT EXISTS `Attendance` (
	`Attendance_ID` int AUTO_INCREMENT NOT NULL UNIQUE,
	`Employee_ID` int NOT NULL,
	`Work_Date` date NOT NULL,
	`Employee_Status` enum('present ','absent','half','leave') NOT NULL DEFAULT 'leave',
	PRIMARY KEY (`Attendance_ID`)
);

CREATE TABLE IF NOT EXISTS `Payroll` (
	`Salary_ID` int AUTO_INCREMENT NOT NULL UNIQUE,
	`Employee_ID` int NOT NULL,
	`Payment_Date` date NOT NULL,
	`Total_Working_Days` int NOT NULL,
	`Present_Days` int NOT NULL,
	`Unpaid_Leaves` int NOT NULL,
	`Paid_Leaves` int NOT NULL,
	`Half_Days` int NOT NULL,
	`Base_Salary` decimal(10,2) NOT NULL,
	`Net_Salary` decimal(10,2) NOT NULL,
	PRIMARY KEY (`Salary_ID`)
);