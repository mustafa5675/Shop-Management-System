CREATE DATABASE Shop_Management;
USE Shop_Management;

CREATE TABLE Sales (
    SaleID INT PRIMARY KEY AUTO_INCREMENT,
    SaleDate DATE DEFAULT CURRENT_TIMESTAMP,
    CustomerID INT,
    ProductID INT NOT NULL,
    Quantity INT NOT NULL,
    UnitPrice DECIMAL(10) NOT NULL,
    TotalAmount DECIMAL(10) GENERATED ALWAYS AS (Quantity * UnitPrice) STORED,
    PaymentMethod ENUM("cash","card","online"),
    
    FOREIGN KEY (CustomerID) REFERENCES Customers(CustomerID),
    FOREIGN KEY (ProductID) REFERENCES Products(ProductID)
);

CREATE TABLE SalesReturn (
    ReturnID INT PRIMARY KEY AUTO_INCREMENT,
    SaleID INT NOT NULL,
    CustomerID INT NOT NULL,
    ProductID INT NOT NULL,
    EmployeeID INT,
    ReturnDate DATE DEFAULT CURRENT_TIMESTAMP,
    QuantityReturned INT NOT NULL,
    RefundAmount DECIMAL(10,2) NOT NULL,
    Reason VARCHAR(255),
    Status ENUM('pending','approved','rejected') DEFAULT 'pending',

    FOREIGN KEY (SaleID) REFERENCES Sales(SaleID),
    FOREIGN KEY (CustomerID) REFERENCES Customers(CustomerID),
    FOREIGN KEY (ProductID) REFERENCES Products(ProductID),
    FOREIGN KEY (EmployeeID) REFERENCES Employees(EmployeeID)
);

CREATE TABLE Customers (
    CustomerID INT PRIMARY KEY AUTO_INCREMENT,
    FirstName VARCHAR(50) NOT NULL,
    LastName VARCHAR(50),
    Email VARCHAR(100) UNIQUE,
    PhoneNumber DECIMAL(15,0),
    Address VARCHAR(10000),
    City VARCHAR(50),
    State VARCHAR(50),
    PostalCode DECIMAL(10,0),
    Country VARCHAR(50),
    RegistrationDate DATE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE Purchases (
    PurchaseID INT PRIMARY KEY AUTO_INCREMENT,
    InvoiceNumber VARCHAR(50) NOT NULL,       -- vendor’s bill/invoice number
    PurchaseDate DATE DEFAULT CURRENT_TIMESTAMP,
    VendorID INT NOT NULL,
    ProductID INT NOT NULL,
    Quantity INT NOT NULL,
    UnitCost DECIMAL(10,2) NOT NULL,
    TotalAmount DECIMAL(10,2) GENERATED ALWAYS AS (Quantity * UnitCost) STORED,

    -- credit terms
    CreditPeriodDays INT,                     -- can override vendor’s default
    DueDate DATE GENERATED ALWAYS AS (
        DATE_ADD(PurchaseDate, INTERVAL COALESCE(CreditPeriodDays, 0) DAY)
    ) STORED,

    IsPaid BOOLEAN DEFAULT FALSE,
    PaymentDate DATE NULL,
    PaymentMethod ENUM('cash','card','online','credit') DEFAULT 'credit',

    FOREIGN KEY (VendorID) REFERENCES Vendors(VendorID),
    FOREIGN KEY (ProductID) REFERENCES Products(ProductID)
);

CREATE TABLE PurchaseReturn (
    PurchaseReturnID INT PRIMARY KEY AUTO_INCREMENT,
    PurchaseID INT NOT NULL,
    VendorID INT NOT NULL,
    ProductID INT NOT NULL,
    EmployeeID INT NULL,
    ReturnDate DATETIME DEFAULT CURRENT_TIMESTAMP,
    QuantityReturned INT NOT NULL,
    RefundAmount DECIMAL(10,2) NOT NULL,
    Reason VARCHAR(255),
    Status ENUM('pending','approved','rejected') DEFAULT 'pending',

    FOREIGN KEY (PurchaseID) REFERENCES Purchases(PurchaseID),
    FOREIGN KEY (VendorID) REFERENCES Vendors(VendorID),
    FOREIGN KEY (ProductID) REFERENCES Products(ProductID),
    FOREIGN KEY (EmployeeID) REFERENCES Employees(EmployeeID)
);

CREATE TABLE Vendors (
    VendorID INT PRIMARY KEY AUTO_INCREMENT,
    FirstName VARCHAR(50) NOT NULL,
    LastName VARCHAR(50),
    Email VARCHAR(100) UNIQUE,
    PhoneNumber DECIMAL(15,0),
    Address VARCHAR(10000),
    City VARCHAR(50),
    State VARCHAR(50),
    PostalCode DECIMAL(10,0),
    Country VARCHAR(50),
    RegistrationDate DATE DEFAULT CURRENT_TIMESTAMP,
	CreditPeriodDays INT   -- vendor’s standard credit terms
);

CREATE TABLE CashRegister (
    CashTxnID INT PRIMARY KEY AUTO_INCREMENT,
    TxnDate DATETIME DEFAULT CURRENT_TIMESTAMP,
    TxnType ENUM('in','out') NOT NULL,           -- inflow or outflow of cash
    TxnCategory ENUM('sale','sales_return','purchase','purchase_return','payroll','other') NOT NULL,
    ReferenceID INT,                             -- ID of Sale, Purchase, Return, or Payroll
    EmployeeID INT,                              -- who processed it
    Description VARCHAR(255),
    Amount DECIMAL(10,2) NOT NULL,
    BalanceAfterTxn DECIMAL(12,2),
    
    FOREIGN KEY (EmployeeID) REFERENCES Employees(EmployeeID)
);

CREATE TABLE BankRegister (
    BankTxnID INT PRIMARY KEY AUTO_INCREMENT,
    TxnDate DATETIME DEFAULT CURRENT_TIMESTAMP,
    TxnType ENUM('in','out') NOT NULL,           -- credit (in) / debit (out)
    TxnCategory ENUM('sale','sales_return','purchase','purchase_return','payroll','other') NOT NULL,
    ReferenceID INT,                             -- ID of Sale, Purchase, Return, or Payroll
    EmployeeID INT,                              -- who processed it
    PaymentMethod ENUM('card','online') NOT NULL,
    Description VARCHAR(255),
    Amount DECIMAL(10,2) NOT NULL,
    BalanceAfterTxn DECIMAL(12,2),
    
    FOREIGN KEY (EmployeeID) REFERENCES Employees(EmployeeID)
);

CREATE TABLE Employees (
    EmployeeID INT PRIMARY KEY AUTO_INCREMENT,
    FirstName VARCHAR(50),
    LastName VARCHAR(50),
    Email VARCHAR(100),
    PhoneNumber DECIMAL(15,0),
    Address VARCHAR(10000),
    City VARCHAR(50),
    State VARCHAR(50),
    PostalCode DECIMAL(10,0),
    Country VARCHAR(50),
    HireDate DATE,
    Salary DECIMAL(10,0)
);

CREATE TABLE Attendance (
    AttendanceID INT PRIMARY KEY AUTO_INCREMENT,
    EmployeeID INT NOT NULL,
    WorkDate DATE NOT NULL,
    Status ENUM('present','absent','leave') NOT NULL,
    
    FOREIGN KEY (EmployeeID) REFERENCES Employees(EmployeeID)
);

CREATE TABLE Payroll (
    PayrollID INT PRIMARY KEY AUTO_INCREMENT,
    EmployeeID INT NOT NULL,
    MonthYear VARCHAR(7) NOT NULL,  -- e.g. '2025-08'
    TotalWorkingDays INT NOT NULL,
    PresentDays INT NOT NULL,
    PaidLeaves INT NOT NULL,
    UnpaidAbsents INT NOT NULL,
    BaseSalary DECIMAL(10,2) NOT NULL,  -- taken from Employees.Salary
    NetSalary DECIMAL(10,2) NOT NULL,   -- calculated after cutting unpaid days
    PaymentDate DATETIME DEFAULT CURRENT_TIMESTAMP,
    BankTxnID INT,  -- link to BankRegister
    
    FOREIGN KEY (EmployeeID) REFERENCES Employees(EmployeeID),
    FOREIGN KEY (BankTxnID) REFERENCES BankRegister(BankTxnID)
);

CREATE TABLE Inventory (
    ProductID INT NOT NULL UNIQUE,
    QuantityInStock INT NOT NULL DEFAULT 0,
    LastUpdated DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
