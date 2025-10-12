# File: gipcco_project/inventory/models/sub_ledger_banking.py
- **Purpose:** Defines models for banking and sub-ledger details related to employees.

- `BankAccount`: Represents a company bank account or a physical cash box.
- `Payment`: Represents a payment transaction, either money in or money out.
- `Employee`: Represents an employee, acts as a sub-ledger for employee-related accounts.
- `EmployeeAdvance`: Represents a single disbursement of funds to an employee.
- `EmployeeAdvanceSettlement`: Connects an expense or inventory receipt to an employee advance.
