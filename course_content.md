=== SECTION: General Accounting ===

ENTITIES:
- Account: name, type (Asset, Liability, Equity, Revenue, Expense), balance
- Chart of Accounts: list of all accounts for a company
- General Ledger: a record containing all accounts
- Transaction (Journal Entry): date, description, list of debits and credits
- Financial Statement: type (Income Statement, Balance Sheet, etc.), period/date

RULES:
- All transactions must use double-entry accounting (affect at least two accounts).
- Total debits must equal total credits for every transaction.
- Accrual Basis: Revenues are recorded when earned, expenses are recorded when incurred.
- Revenue Recognition Principle: Record revenue when it is earned, regardless of when cash is received.
- Matching Principle (Expense Recognition Principle): Match expenses to the revenues they helped generate in the same period.
- Cost Principle: Assets are recorded at their original cost and are not increased for market value changes.
- Conservatism Principle: Assets may be reported at less than cost if value is impaired, but not more.
- Assets are increased with a debit and decreased with a credit.
- Liabilities and Equity are increased with a credit and decreased with a debit.
- Revenues are increased with a credit.
- Expenses are increased with a debit.
- Land is not depreciated.
- Internally generated intangible assets (e.g., reputation, logos) are not recorded as an asset.

CALCULATIONS:
- Accounting Equation = Assets = Liabilities + Stockholders' Equity
- Stockholders' Equity = Assets - Liabilities
- Net Income / Net Loss = Revenues - Expenses
- Retained Earnings (ending) = Retained Earnings (beginning) + Net Income - Dividends
- Asset Carrying Amount (Book Value) = Original Cost - Accumulated Depreciation

WORKFLOWS:
- Recording a Transaction: Identify accounts involved → Determine debit/credit for each account → Record entry ensuring debits equal credits.
- End-of-Period Closing: Transfer balances from all revenue and expense accounts to Retained Earnings → Reset revenue and expense account balances to zero for the next period.
- Handling Prepayments (e.g., Insurance): Debit a prepaid asset account when paid → At end of period, credit the asset account and debit an expense account for the portion used up.
- Handling Unearned Revenue: Credit an unearned revenue liability account when cash is received in advance → As service is delivered, debit the liability account and credit a revenue account.

CLASSIFICATIONS:
- Account Types: Assets, Liabilities, Stockholders' Equity, Revenues, Expenses
- Assets: Cash, Accounts Receivable, Supplies, Equipment, Vehicles, Prepaid Insurance, Land
- Liabilities: Notes Payable, Accounts Payable, Wages Payable, Interest Payable, Unearned Revenue
- Stockholders' Equity: Common Stock, Retained Earnings
- Cash Flow Activities: Operating, Investing, Financing

REPORTS:
- Income Statement: Shows revenues, expenses, and net income/loss over a period of time.
- Balance Sheet: A snapshot showing assets, liabilities, and stockholders' equity at a specific point in time.
- Statement of Cash Flows: Shows cash changes from operating, investing, and financing activities over a period of time.

STATES:
- [No explicit states like "Draft" or "Posted" were mentioned in the source material.]



=== SECTION: Core Accounting Engine ===

ENTITIES:
- Account: name, type (Asset, Liability, etc.), normal balance (Debit/Credit)
- Chart of Accounts: an ordered list of all accounts
- Journal Entry: date, description, lines
- Journal Line: account, debit amount, credit amount

RULES:
- A transaction must affect at least two accounts.
- The total debit amount must equal the total credit amount for every journal entry.
- Asset, Expense, Loss, and Dividend/Draw accounts are increased with a debit and decreased with a credit (Normal Debit Balance).
- Liability, Equity, Revenue, Gain, and Income accounts are increased with a credit and decreased with a debit (Normal Credit Balance).
- Contra accounts have a normal balance opposite to their parent account type (e.g., Sales Returns is a contra-revenue account with a debit balance).
- When cash is received, the Cash account is debited.
- When cash is paid, the Cash account is credited.

CALCULATIONS:
- Account Balance = Sum of entries on the normal balance side - sum of entries on the opposite side.

WORKFLOWS:
- Recording a Transaction: Identify accounts involved → Determine which accounts to debit and credit → Create a journal entry with equal total debits and credits.
- Closing Temporary Accounts (Year-End): Transfer balances from all temporary accounts (Revenues, Expenses, Draws) to a permanent equity account (e.g., Retained Earnings) → Start the new year with zero balances in all temporary accounts.

CLASSIFICATIONS:
- Account Categories: Assets, Liabilities, Owner's Equity, Revenues, Expenses, Gains, Losses, Dividends/Draws.
- Account Duration:
    - Permanent (Real) Accounts: Assets, Liabilities, Equity. Balances carry forward.
    - Temporary (Nominal) Accounts: Revenues, Expenses, Draws. Balances are closed at year-end.

REPORTS:
- Balance Sheet: shows Assets, Liabilities, and Equity at a specific point in time.
- Income Statement: shows Revenues, Expenses, Gains, and Losses over a period of time.

STATES:
- Temporary Account: Active (during period) → Closed (at year-end, balance is zero).


=== SECTION: Chart of Accounts ===

ENTITIES:
- Account: number, name, type, description, normal balance (Debit/Credit), associated organizational unit (department, division, product line)

RULES:
- Account numbers must be unique.
- The account numbering scheme must allow for gaps to add new accounts.
- Unused accounts can be deleted.
- Every transaction must use a minimum of two accounts.

WORKFLOWS:
- Assisted Transaction Entry (Check Writing Example): System auto-generates one side of the entry (credit to cash) → User selects the account for the other side (debit to expense).
- Chart of Accounts Management: Start with template → Modify for business needs → Add/delete accounts as required.

CLASSIFICATIONS:
- Primary Account Types: Assets, Liabilities, Equity, Revenue, Cost of Goods Sold, Expenses, Gains, Losses.
- Asset Sub-types: Current Assets; Property, Plant, and Equipment.
- Liability Sub-types: Current Liabilities, Long-term Liabilities.
- Hierarchical Grouping: Accounts can be categorized by business function, department, division, or product line.

REPORTS:
- Chart of Accounts List: A listing of all accounts showing number, name, and type.

NOTES:
- The account number structure can encode information (e.g., first digit for account type, subsequent digits for department).
- An account's "normal balance" dictates how it's affected by debits/credits:
    - Debit Increase: Assets, Expenses
    - Credit Increase: Liabilities, Equity, Revenues
- The system should provide sample/template charts of accounts.
- Account numbers may be optional for some configurations (e.g., small businesses).


=== SECTION: Core Accounting Engine ===

ENTITIES:
- General Ledger: a collection of all accounts for a company
- Chart of Accounts: a list of all available accounts
- Account: number, name, type, category, description, normal balance (Debit/Credit), balance
- Journal Entry: date, description, status, type (regular, adjusting, closing, reversing)
- Journal Line: account, debit amount, credit amount

RULES:
- Every transaction must affect at least two accounts.
- The total debit amount must equal the total credit amount in every journal entry.
- The accounting equation must always be in balance: Assets = Liabilities + Equity.
- Asset accounts normally have debit balances.
- Liability accounts normally have credit balances.
- Equity accounts normally have credit balances.
- Revenue accounts normally have credit balances.
- Expense accounts normally have debit balances.
- Contra accounts have a balance opposite to their normal classification (e.g., Accumulated Depreciation is a contra-asset with a credit balance).

CALCULATIONS:
- Account Balance = sum of all debits - sum of all credits (for debit-balance accounts) OR sum of all credits - sum of all debits (for credit-balance accounts)

---
=== SECTION: Transaction Workflows ===

WORKFLOWS:
- Posting a Journal Entry: Validate debit equals credit → Update balances of affected accounts → Mark entry as "Posted" → Lock entry from editing/deletion.
- Accounts Payable: Enter vendor invoice → Debit an expense or asset account, Credit Accounts Payable → Process payment → Debit Accounts Payable, Credit Cash.
- Accounts Receivable: Create customer invoice → Debit Accounts Receivable, Credit a Revenue account → Receive payment → Debit Cash, Credit Accounts Receivable.
- Bank Reconciliation: Compare bank statement balance to GL Cash account balance → Identify reconciling items (outstanding checks, deposits in transit, bank fees) → Create adjusting journal entries for items recorded by bank but not in GL (e.g., service charges) → Reconciled when adjusted bank balance equals adjusted GL cash balance.

STATES:
- Journal Entry: Draft → Posted

---
=== SECTION: Period-End Processes ===

ENTITIES:
- Adjusting Journal Entry: an entry to record accruals, deferrals, or estimates at the end of a period
- Closing Journal Entry: an entry to zero out temporary (income statement) accounts at year-end
- Reversing Journal Entry: an optional entry to reverse a prior period's accrual-type adjusting entry

RULES:
- Closing entries transfer the net balance of all income statement accounts to Retained Earnings (or Owner's Capital).
- Income statement accounts must start the new accounting year with a zero balance.
- Balance sheet account balances carry forward to the next accounting period.
- Reversing entries are dated the first day of the new accounting period.

WORKFLOWS:
- Month/Year-End Close: Ensure all transactions are recorded → Post all adjusting entries → Generate financial statements → (Year-End) Post closing entries.

---
=== SECTION: Account Classifications ===

CLASSIFICATIONS:
- Balance Sheet Accounts (Permanent Accounts)
  - Assets: Current Assets (Cash, Accounts Receivable, Inventory, Prepaid Expenses), Long-term Investments, Property, Plant & Equipment (Land, Buildings, Equipment), Intangible Assets
  - Liabilities: Current Liabilities (Accounts Payable, Accrued Expenses, Unearned Revenue), Noncurrent Liabilities (Loans Payable, Bonds Payable)
  - Equity: Paid-in Capital (Common Stock), Retained Earnings, Treasury Stock
- Income Statement Accounts (Temporary Accounts)
  - Operating Revenues: Sales, Service Revenue
  - Operating Expenses: Cost of Goods Sold, Salaries Expense, Rent Expense, Depreciation Expense
  - Non-operating Revenues & Gains: Interest Income, Gain on Sale of Asset
  - Non-operating Expenses & Losses: Interest Expense, Loss on Sale of Asset

---
=== SECTION: Financial Reporting ===

REPORTS:
- Trial Balance: Lists every account and its debit or credit balance. Total debits must equal total credits.
- Income Statement (P&L): Revenues, expenses, gains, and losses over a period of time.
- Balance Sheet: Assets, liabilities, and equity at a specific point in time.
- Statement of Cash Flows: Cash inflows and outflows from operating, investing, and financing activities over a period.
- Statement of Stockholders' Equity: Changes in each equity account over a period.

CALCULATIONS:
- Net Income = All Revenues & Gains - All Expenses & Losses
- Gross Profit = Sales - Cost of Goods Sold
- Operating Income = Gross Profit - Operating Expenses
- Retained Earnings (ending) = Retained Earnings (beginning) + Net Income - Dividends
- Book Value of an Asset = Asset's original cost - Accumulated Depreciation
- Working Capital = Current Assets - Current Liabilities
- Net Change in Cash = Cash from Operating + Cash from Investing + Cash from Financing Activities



=== SECTION: Core Accounting Logic ===

**ENTITIES:**
- General Ledger Account: name, type (Asset, Liability, Equity, Revenue, Expense, etc.), normal balance (debit/credit), contra status
- Transaction (Journal Entry): date, description
- Transaction Line (Journal Line): account, debit amount, credit amount
- Business Entity: type (Sole Proprietorship, Corporation)

**RULES:**
- For every transaction, total debits must equal total credits.
- The accounting equation must always remain in balance: Assets = Liabilities + Equity.
- Asset accounts normally have debit balances.
- Liability and Equity accounts normally have credit balances.
- Revenue accounts increase with a credit.
- Expense accounts increase with a debit.
- Contra accounts have a balance opposite to their parent account type (e.g., Owner's Draws, Treasury Stock).

**CALCULATIONS:**
- Basic Accounting Equation: Assets = Liabilities + Equity
- Equity = Assets - Liabilities
- Net Income = Total Revenues - Total Expenses
- Expanded Equation (Sole Prop.): Assets = Liabilities + Owner's Capital + Revenues - Expenses - Owner's Draws
- Expanded Equation (Corp.): Assets = Liabilities + Paid-in Capital + Revenues - Expenses - Dividends - Treasury Stock
- Ending Owner's Equity = Beginning Equity + Owner Investments + Net Income - Owner Draws

**WORKFLOWS:**
- Recording a Transaction: Create a journal entry with equal debits and credits affecting two or more general ledger accounts.
- Closing Period Accounts: Transfer balances from temporary accounts (Revenues, Expenses) to a permanent equity account (Owner's Capital or Retained Earnings).
- Calculating Missing Net Income:
    1. Determine beginning and ending equity using Assets - Liabilities.
    2. Apply the `Ending Owner's Equity` formula.
    3. Solve for the unknown Net Income amount.

**CLASSIFICATIONS:**
- Account Types:
    - Assets: Cash, Accounts Receivable, Equipment
    - Liabilities: Notes Payable, Accounts Payable
    - Owner's Equity (Sole Proprietorship): Capital, Drawing (contra)
    - Stockholders' Equity (Corporation): Common Stock, Retained Earnings, Treasury Stock (contra)
    - Revenues: Service Revenues
    - Expenses: Advertising Expense, Temp Service Expense
- Account Natures:
    - Permanent Accounts: Assets, Liabilities, Equity (appear on Balance Sheet)
    - Temporary Accounts: Revenues, Expenses (appear on Income Statement)

**REPORTS:**
- Balance Sheet: A snapshot of Assets, Liabilities, and Equity at a single point in time.
- Income Statement: A summary of Revenues and Expenses over a period of time to calculate Net Income/Loss.
- Statement of Changes in Owner's Equity: A report showing how Owner's Equity changed over a period due to investments, net income/loss, and draws.

**STATES:**
- (No explicit states like "Draft" or "Posted" are mentioned in the material.)



=== SECTION: Core Accounting Engine ===

ENTITIES:
- Chart of Accounts: account number, name, type, category
- Account: An individual general ledger account
- Journal Entry: entry number, date, description, status
- Journal Line: account, debit amount, credit amount
- Asset: description, acquisition date, historical cost, book value
- Liability: description, origination date, amount

RULES:
- Debits must equal credits in every journal entry.
- Posted transactions cannot be edited or deleted.
- Business transactions must be kept separate from the owner's personal transactions.
- All transactions for an entity must be recorded in a single monetary unit.

CALCULATIONS:
- Account Balance = A running total of debits and credits based on the account's normal balance.
- Book Value (Asset) = Historical Cost - Accumulated Depreciation.

WORKFLOWS:
- Posting a Journal Entry: Create draft entry → Validate debits equal credits → Post entry → Update account balances → Lock entry from editing.

CLASSIFICATIONS:
- Account Types: Asset, Liability, Equity, Revenue, Expense

STATES:
- Journal Entry: Draft → Posted

=== SECTION: Accrual & Matching ===

ENTITIES:
- Adjusting Journal Entry: A journal entry for period-end accruals, deferrals, or systematic allocations like depreciation.

RULES:
- Revenue must be recognized when it is earned.
- Expenses must be matched to the period in which the corresponding revenue was earned.
- If an expense cannot be directly matched to revenue, it is recognized in the period it is incurred or used up.
- Revenue received before it is earned must be recorded as a liability (Deferred Revenue).
- Expenses incurred before they are paid must be recorded as a liability (Accrued Expense).
- Payments made for future expenses must be recorded as an asset (Prepaid Expense).

WORKFLOWS:
- Recognizing Deferred Revenue: Receive cash → Create liability (Deferred Revenue) → As revenue is earned, create adjusting entry to reduce liability and recognize revenue.
- Recognizing Prepaid Expense: Pay cash → Create asset (Prepaid Expense) → As asset is used, create adjusting entry to reduce asset and recognize expense.
- Accruing Expenses: Incur expense → Create adjusting entry to recognize expense and create liability → Pay cash → Reduce liability.
- Accruing Revenue: Earn revenue → Create adjusting entry to recognize revenue and create asset (Receivable) → Receive cash → Reduce asset.

=== SECTION: Financial Reporting & Period-End ===

ENTITIES:
- Accounting Period: name, start date, end date, status (Open, Closed)
- Financial Statement Note: text content, associated report
- Company / Economic Entity: name, going concern status (can be a single legal entity or a consolidated group)

RULES:
- Transactions cannot be posted to a closed accounting period.
- A complete set of financial statements must be produced for external reporting.
- Financial statements must include notes with required disclosures.

CALCULATIONS:
- Total Assets = Total Liabilities + Total Stockholders' Equity
- Net Income = Total Revenues - Total Expenses

WORKFLOWS:
- Period-End Closing: Perform all adjusting entries → Generate financial statements → Close temporary (income statement) accounts → Mark accounting period as "Closed".

REPORTS:
- Balance Sheet: Assets, Liabilities, and Equity at a specific point in time.
- Income Statement: Revenues and Expenses over a specific period.
- Statement of Stockholders' Equity: Changes in equity over a period.
- Statement of Cash Flows: Cash inflows and outflows over a period.
- Notes to the Financial Statements: Disclosures required for context and completeness.

STATES:
- Accounting Period: Open → Closed

=== SECTION: Governing Principles & Policies ===

RULES:
- Cost Principle: Assets must be recorded and maintained at their original historical cost.
- Conservatism Principle: When two acceptable accounting methods exist, the one less likely to overstate assets or income must be chosen.
- Consistency Principle: Accounting methods must be applied consistently across periods; changes must be disclosed.
- Materiality Principle: Accounting rules may be ignored for amounts that are insignificant.
- Going Concern Principle: If an entity is not expected to continue operating, it must be disclosed and its assets must be valued at liquidation value.
- Impairment: If an asset's fair value drops below its book value, an impairment loss must be recognized.
- Internally developed intangible assets (e.g., brands, logos) cannot be recorded as assets on the balance sheet.

STATES:
- Company: Going Concern → Not a Going Concern




=== SECTION: Core Accounting Logic ===

### ENTITIES
- `Account`: name, type (Asset, Liability, Equity, Revenue, Expense, Gain, Loss)
- `Transaction`: unique identifier, date, description
- `Transaction Line`: associated transaction, account, debit amount, credit amount

### RULES
- Every transaction must affect at least two accounts.
- For every transaction, total debits must equal total credits.
- Assets must always equal Liabilities + Stockholders' Equity.
- Revenue is recognized when earned, not when cash is received (Accrual Basis).
- Expenses are recognized when incurred, not when paid (Accrual Basis).

### CALCULATIONS
- `Net Income` = Revenues - Expenses + Gains - Losses
- `Comprehensive Income` = Net Income + Other Comprehensive Income
- `Total Assets` = Sum of all asset account balances
- `Total Liabilities` = Sum of all liability account balances
- `Total Equity` = Sum of all equity account balances

### WORKFLOWS
- `Transaction Recording`: A financial event occurs → a transaction is created with balanced debit and credit lines → account balances are updated → data is summarized for reporting.

### CLASSIFICATIONS
- `Balance Sheet Categories`: Assets, Liabilities, Stockholders' Equity
- `Income Statement Categories`: Revenues, Expenses, Gains, Losses
- `Cash Flow Categories`: Operating Activities, Investing Activities, Financing Activities

### REPORTS
- `Income Statement`: Presents revenues, expenses, gains, and losses over a period.
- `Balance Sheet`: Presents assets, liabilities, and stockholders' equity at a specific date.
- `Statement of Cash Flows`: Explains the change in cash from operating, investing, and financing activities over a period.
- `Statement of Stockholders' Equity`: Lists the changes in stockholders' equity over a period.
- `Statement of Comprehensive Income`: Presents Net Income and Other Comprehensive Income over a period.

### STATES
- [No specific states for transactions, like Draft or Posted, are mentioned in the material.]



=== SECTION: Core Accounting ===

ENTITIES:
- General Ledger Account: account number, name, type (Asset, Liability, etc.), normal balance (Debit/Credit), balance
- Journal Entry: date, description, type (e.g., General, Adjusting), status
- Journal Line: account, debit amount, credit amount

RULES:
- Debits must equal credits in every journal entry.
- Each adjusting entry must affect at least one balance sheet account and one income statement account.
- Revenues must be recorded in the period they are earned.
- Expenses must be recorded in the period they are incurred.
- Income statement account balances are reset to zero at the start of a new accounting year.
- Balance sheet account balances carry forward to the next accounting year.

WORKFLOWS:
- Period-End Adjustment Process: Review preliminary balances → Identify required adjustments → Create and post adjusting journal entries → Generate financial statements.
- Closing Process (Year-End): Transfer net income/loss to equity → Reset all revenue and expense account balances to zero.

STATES:
- Account Balance: Preliminary → Adjusted

---

=== SECTION: Adjusting Entries ===

CALCULATIONS:
- Supplies Used = Beginning supplies balance - Ending supplies on hand
- Expired Prepaid Expense = Total prepaid amount - Unexpired portion
- Accrued Interest = Principal x Rate x Time period
- Depreciation Expense = (Cost of asset / useful life) for the period
- Bad Debt Expense = An estimated amount of uncollectible receivables
- Net Realizable Value of Receivables = Accounts Receivable - Allowance for Doubtful Accounts

WORKFLOWS:
- Accruing Revenue: Debit Accounts Receivable, Credit Service Revenues for work performed but not yet billed.
- Accruing Expense: Debit an Expense account, Credit a Payable account for expenses incurred but not yet paid/billed (e.g., Interest, Wages, Repairs).
- Recognizing Earned Revenue (from Deferral): Debit Unearned Revenues, Credit Service Revenues for the portion of services delivered.
- Recognizing Used Expense (from Deferral): Debit an Expense account, Credit a Prepaid Asset account for the portion of the asset used up (e.g., Insurance, Supplies).
- Recording Bad Debt: Debit Bad Debts Expense, Credit Allowance for Doubtful Accounts.
- Recording Depreciation: Debit Depreciation Expense, Credit Accumulated Depreciation.

CLASSIFICATIONS:
- Adjusting Entry Types:
  - Accruals: Recording a revenue or expense before cash is exchanged.
  - Deferrals: Splitting a previously recorded cash transaction between two or more accounting periods.

---

=== SECTION: Accounts & Classifications ===

CLASSIFICATIONS:
- Account Types:
  - Assets: Cash, Accounts Receivable, Supplies, Prepaid Insurance, Equipment
  - Contra-Assets: Accumulated Depreciation, Allowance for Doubtful Accounts
  - Liabilities: Accounts Payable, Notes Payable, Interest Payable, Wages Payable, Unearned Revenues
  - Owner's Equity
  - Revenues: Service Revenues
  - Expenses: Bad Debts Expense, Depreciation Expense, Insurance Expense, Interest Expense, Repairs & Maintenance Expense, Supplies Expense, Wages Expense

---

=== SECTION: Reporting ===

REPORTS:
- Income Statement: Shows Revenues and Expenses over a period of time.
- Balance Sheet: Shows Assets, Liabilities, and Equity at a specific point in time.
- Aging of Accounts Receivable: Lists unpaid customer invoices sorted by date to determine how old they are.




=== SECTION: Core Accounting ===

ENTITIES:
- General Ledger Account: account number, account name, account type, category, balance
- Journal Entry: date, description, status (e.g., Draft, Posted)
- Journal Line: journal entry ID, account, debit amount, credit amount
- Accounting Period: start date, end date, status (e.g., Open, Closed)
- Company: legal name
- Subsidiary: parent company ID [?]

RULES:
- The accounting equation must always be in balance: Assets = Liabilities + Stockholders’ Equity.
- Each journal entry must have total debits equal to total credits.
- Must comply with accrual method of accounting: revenues are recognized when earned, expenses are recognized when incurred, regardless of cash movement.
- Historical cost principle: assets and expenses are recorded at their original transaction cost.
- Matching principle: expenses must be matched to the revenues they helped generate in the same accounting period.
- Posted transactions cannot be edited or deleted; they must be reversed with a new entry.
- A period must be closed before financial statements can be finalized.
- For consolidated statements, all inter-company transactions must be eliminated.

CALCULATIONS:
- Account Balance = Sum of all debits - Sum of all credits (for asset/expense accounts) OR Sum of all credits - Sum of all debits (for liability/equity/revenue accounts).
- Gross Profit = Net Sales - Cost of Goods Sold
- Net Income = Revenues - Expenses + Gains - Losses
- Comprehensive Income = Net Income + Other Comprehensive Income (OCI)
- Change in Retained Earnings = Net Income - Dividends
- Ending Retained Earnings = Beginning Retained Earnings + Net Income - Dividends
- Stockholders' Equity = Assets - Liabilities
- Stockholders' Equity = Paid-in Capital + Retained Earnings + Accumulated Other Comprehensive Income - Treasury Stock
- Earnings Per Share (EPS) = Net Income / Weighted-average number of common shares outstanding
- Working Capital = Current Assets - Current Liabilities
- Current Ratio = Current Assets / Current Liabilities
- Free Cash Flow = Cash from Operating Activities - Capital Expenditures

WORKFLOWS:
- Period-End Closing: Record adjusting entries (e.g., depreciation, accruals) → Validate all journal entries → Run trial balance → Generate financial statements → Close the period.
- Net Income to Balance Sheet Link: Calculate Net Income on Income Statement → Transfer Net Income amount to update Retained Earnings on the Statement of Stockholders' Equity → Use ending Retained Earnings balance on the Balance Sheet.
- OCI to Balance Sheet Link: Calculate OCI on Statement of Comprehensive Income → Transfer OCI amount to update Accumulated OCI on the Statement of Stockholders' Equity → Use ending Accumulated OCI balance on the Balance Sheet.
- Cash Flow from Operations (Indirect Method): Start with Net Income → Add back non-cash expenses (e.g., depreciation) → Adjust for gains/losses on asset sales → Adjust for changes in current asset and current liability account balances.

CLASSIFICATIONS:
- Account Types: Asset, Liability, Equity, Revenue, Expense, Gain, Loss
- Asset Categories: Current Assets, Investments (long-term), Property, Plant and Equipment, Other Assets
- Liability Categories: Current Liabilities, Noncurrent (Long-term) Liabilities
- Stockholders' Equity Components: Paid-in Capital, Retained Earnings, Accumulated Other Comprehensive Income, Treasury Stock (contra-equity)
- Statement of Cash Flows Sections: Operating Activities, Investing Activities, Financing Activities

REPORTS:
- Income Statement (Statement of Earnings): Reports Revenues, Expenses, Gains, Losses, and Net Income over a period of time. Must show Earnings Per Share if public.
- Statement of Comprehensive Income: Reports Net Income and Other Comprehensive Income (OCI) over a period.
- Balance Sheet (Statement of Financial Position): Reports Assets, Liabilities, and Stockholders' Equity at a specific point in time. Must be a classified balance sheet (current vs. non-current).
- Statement of Stockholders' Equity: Shows changes in each component of stockholders' equity over a period. Reconciles beginning and ending balances.
- Statement of Cash Flows: Reports cash inflows and outflows from Operating, Investing, and Financing activities over a period. Must reconcile beginning and ending cash balances.
- Notes to the Financial Statements: Required supplementary disclosures providing detail for amounts on the primary statements.
- Comparative Financial Statements: All reports must support showing amounts for the current period alongside one or more prior periods.
- Consolidated Financial Statements: Reports must combine the financial data of a parent company and its subsidiaries as a single economic entity.

STATES:
- Accounting Period: Open → Closed
- Journal Entry: Draft → Posted
- Financial Statements: Unaudited → Audited [?]





=== SECTION: Balance Sheet ===

**ENTITIES:**
-   **Account:** name, type (Asset, Liability, Equity), balance
-   **Balance Sheet Report:** company name, title, date (point in time)
-   **Asset:** historical cost, description
-   **Contra Asset Account:** an account that reduces the balance of a related asset (e.g., Accumulated Depreciation, Allowance for Doubtful Accounts)
-   **Liability:** amount, due date
-   **Equity Account (Corporation):** Common Stock, Retained Earnings, Treasury Stock, Accumulated Other Comprehensive Income
-   **Equity Account (Sole Proprietorship):** Owner's Capital, Owner's Drawing
-   **Financial Statement Note:** referenced text providing additional detail

**RULES:**
-   The accounting equation must always balance: Assets = Liabilities + Equity
-   The Balance Sheet date is a single point in time, not a period
-   Assets must be recorded at historical cost, not current market value
-   Internally developed intangible assets (e.g., brands) cannot be recorded as assets
-   Land is not depreciated
-   Goodwill is not amortized but must be tested for impairment
-   The portion of long-term debt principal due within one year must be reclassified as a current liability
-   Treasury stock is a subtraction from total stockholders' equity (a contra-equity account)
-   Owner withdrawals (draws) are not a business expense; they reduce owner's equity directly
-   A contingent loss must be recorded as a liability if the loss is probable and the amount can be estimated
-   Financial statements must include "Notes to the Financial Statements" for full disclosure

**CALCULATIONS:**
-   **Book Value (of Property, Plant & Equipment)** = Asset Cost - Accumulated Depreciation
-   **Net Accounts Receivable** = Total Accounts Receivable - Allowance for Doubtful Accounts
-   **Ending Retained Earnings** = Beginning Retained Earnings + Net Income - Dividends
-   **Ending Owner's Capital** = Beginning Capital + Owner Investments + Net Income - Owner Draws
-   **Working Capital** = Current Assets - Current Liabilities
-   **Current Ratio** = Current Assets / Current Liabilities
-   **Quick Ratio (Acid-Test Ratio)** = (Current Assets - Inventory - Prepaid Expenses) / Current Liabilities
-   **Debt to Equity Ratio** = Total Liabilities / Total Stockholders' Equity
-   **Debt to Total Assets Ratio** = Total Liabilities / Total Assets

**WORKFLOWS:**
-   **Asset Depreciation:** An asset's cost is expensed over its useful life, increasing its Accumulated Depreciation balance
-   **Deferred Revenue Recognition:** Receive cash → Record Deferred Revenue liability. Deliver service/good → Decrease Deferred Revenue liability and recognize Revenue
-   **Prepaid Expense Recognition:** Pay cash → Record Prepaid Expense asset. As service/good is used → Decrease Prepaid Expense asset and recognize Expense
-   **Period-End Closing (Corporation):** Net Income is transferred to the Retained Earnings account
-   **Period-End Closing (Sole Proprietorship):** Net Income and Owner's Draws are transferred to the Owner's Capital account

**CLASSIFICATIONS:**
-   **Assets**
    -   **Current Assets:** Cash and cash equivalents, Short-term investments, Accounts receivable, Inventory, Supplies, Prepaid expenses
    -   **Long-Term (Noncurrent) Assets:** Investments, Property Plant & Equipment, Intangible Assets (Goodwill, Patents), Other Assets
-   **Liabilities**
    -   **Current Liabilities:** Accounts payable, Short-term loans, Current portion of long-term debt, Accrued liabilities, Deferred revenues
    -   **Long-Term (Noncurrent) Liabilities:** Notes payable, Bonds payable, Deferred income taxes
-   **Equity (Corporation)**
    -   Paid-in Capital (e.g., Common Stock)
    -   Retained Earnings
    -   Accumulated Other Comprehensive Income
    -   Treasury Stock (Contra-Equity)
-   **Equity (Sole Proprietorship)**
    -   Owner's Capital
    -   Owner's Drawing

**REPORTS:**
-   **Balance Sheet:** Reports Assets, Liabilities, and Equity at a specific point in time
-   **Comparative Balance Sheet:** Presents balance sheet data for two or more periods side-by-side
-   **Consolidated Balance Sheet:** Combines financial data of a parent company and its subsidiaries
-   **Statement of Stockholders' Equity:** Details the changes in each equity account over a period

**STATES:**
-   **Asset Under Construction:** Construction in Progress → Placed in Service (becomes a depreciable asset)
-   **Contingent Liability:** Possible (Note disclosure) → Probable & Estimable (Recorded as liability)

**NOTES:**
-   Commitments and contingencies are disclosed in notes; they are not recorded with a dollar value on the balance sheet unless specific criteria are met




=== SECTION: Core Accounting & Financial Ratios ===

ENTITIES:
- General Ledger Account: account number, name, type (Asset, Liability, etc.), balance
- Current Asset Account: subtype (Cash, Accounts Receivable, Inventory, etc.)
- Current Liability Account: subtype (Accounts Payable, Accrued Expenses, etc.)
- Accounts Receivable Invoice: customer, issue date, due date, terms (e.g., 2/10, net 30), discount date, discount percent, gross amount, net amount, status
- Allowance for Doubtful Accounts: estimated uncollectible amount
- Inventory Item: cost, quantity on hand
- Accounts Payable Bill: vendor, invoice reference, due date, amount

RULES:
- Current assets must be listed in order of liquidity on reports.
- Transactions affecting only working capital accounts do not change the total amount of working capital.
- Revenue is recognized when earned; expenses are recognized when incurred (Accrual Method).
- Unpaid business credit card balances must be recorded as an accrued liability.
- Cash discounts on invoices are only valid if paid by the discount date.
- A three-way match (invoice, purchase order, receiving report) can be required before creating an accounts payable record.
- On the Statement of Cash Flows, cash inflows are positive, and cash outflows are negative.
- Short-term loan activity is classified under Financing Activities, not Operating Activities.

CALCULATIONS:
- Working Capital = Current Assets - Current Liabilities
- Current Ratio = Current Assets / Current Liabilities
- Quick Assets = Cash + Cash Equivalents + Temporary Investments + Net Accounts Receivable
- Quick Ratio = Quick Assets / Current Liabilities
- Net Accounts Receivable = Gross Accounts Receivable - Allowance for Doubtful Accounts
- Accounts Receivable Turnover Ratio = Net Credit Sales / Average Accounts Receivable
- Average Collection Period = 365 (or 360) days / Accounts Receivable Turnover Ratio
- Inventory Turnover Ratio = Cost of Goods Sold / Average Inventory Cost
- Days' Sales in Inventory = 365 (or 360) days / Inventory Turnover Ratio
- Net Cash Provided by Operating Activities (Indirect) = Net Income + Non-cash Expenses +/- Changes in Working Capital Accounts
- Operating Cash Flow Ratio = Net Cash Provided by Operating Activities / Average Current Liabilities

WORKFLOWS:
- Operating Cycle: Use cash for inventory → Sell inventory (creates Accounts Receivable) → Collect cash from customer

CLASSIFICATIONS:
- Balance Sheet Accounts:
    - Current Assets: Cash & Equivalents, Temporary Investments, Accounts Receivable, Inventory, Supplies, Prepaid Expenses
    - Current Liabilities: Short-term Loans, Accounts Payable, Accrued Expenses/Liabilities, Customer Deposits, Deferred Revenues
- Cash Flow Activities:
    - Operating Activities
    - Investing Activities
    - Financing Activities

REPORTS:
- Classified Balance Sheet: Shows current/long-term assets, current/long-term liabilities, and equity.
- Statement of Cash Flows: Reports cash inflows/outflows from Operating, Investing, and Financing activities.
- Aging of Accounts Receivable: Lists unpaid invoices sorted by time past due (e.g., Current, 1-30 days, 31-60 days).
- Inventory Turnover Report: Shows turnover ratio and days' sales in inventory for total inventory and for each individual item.

STATES:
- Accounts Receivable Invoice: Current → Past Due (1-30 Days) → Past Due (31-60 Days) → etc.

NOTES:
- The calculation of "Quick Ratio" has multiple accepted formulas (e.g., some subtract only inventory, others also subtract supplies and prepaids). The system should support a configurable definition.
- Calculating "average" balances (e.g., Average A/R, Average Inventory) using only beginning and ending balances can be misleading for seasonal businesses. The system should ideally support calculations based on more frequent data points (e.g., monthly balances).





=== SECTION: Core Accounting & Income Statement ===

ENTITIES:
- Account: name, number, type (Asset, Liability, Equity, Revenue, Expense, Gain, Loss, Other Comprehensive Income), category (Operating, Non-operating), cost type (Variable, Fixed Traceable, Fixed Common)
- Long-Term Asset: original cost, accumulated depreciation, book value
- Financial Statement Note: text content, report association

RULES:
- Must use accrual basis of accounting (revenue recognized when earned, expenses when incurred).
- Expenses must be matched to the period's revenues they helped generate.
- For a sole proprietorship, owner's compensation is not an expense; it is a draw from owner's equity.
- Assets are recorded and depreciated based on their historical cost.

CALCULATIONS:
- Net Sales = Gross Sales - Sales Returns - Sales Allowances - Sales Discounts
- Gross Profit = Net Sales - Cost of Sales
- Gross Profit Percentage = Gross Profit / Net Sales
- Operating Income = Gross Profit - Selling, General & Administrative Expenses
- Book Value (of an asset) = Original Cost - Accumulated Depreciation
- Gain on Sale of Asset = Sale Price - Book Value (if positive)
- Loss on Sale of Asset = Book Value - Sale Price (if positive)
- Income Before Income Taxes = Operating Income +/- Nonoperating Revenues, Expenses, Gains, and Losses
- Net Income = Income Before Income Taxes - Income Tax Expense
- Net Loss = (when expenses & losses > revenues & gains)
- Comprehensive Income = Net Income + Other Comprehensive Income
- Contribution Margin = Sales - All Variable Costs and Variable Expenses

WORKFLOWS:
- Period Close (Corporation): Net Income/Loss is transferred to Retained Earnings account → Other Comprehensive Income is transferred to Accumulated Other Comprehensive Income account.
- Period Close (Sole Proprietorship): Net Income/Loss is transferred to Owner's Capital account.

CLASSIFICATIONS:
- Revenue Types: Operating, Non-operating (e.g., Investment Income)
- Expense Types: Operating, Non-operating (e.g., Interest Expense)
- Operating Expenses: Cost of Sales, Selling, General & Administrative (SG&A)
- Other Comprehensive Income Items: Foreign currency adjustments, Unrealized gains/losses on pensions, Unrealized gains/losses on hedging derivatives

REPORTS:
- Income Statement (P&L): Shows revenues, expenses, gains, losses over a period.
    - Structure: Net Sales → Cost of Sales → Gross Profit → SG&A → Operating Income → Non-operating items → Income Before Tax → Tax → Net Income.
    - Features: Must support comparative periods (e.g., 3 columns for 3 years) and rounding of amounts.
- Statement of Comprehensive Income: Shows Net Income and Other Comprehensive Income items.
- Contribution Margin Income Statement (Internal):
    - Structure: Sales → Variable Costs → Contribution Margin → Traceable Fixed Costs → Segment Margin → Common Fixed Costs → Net Income.




=== SECTION: Statement of Cash Flows (SCF) ===

ENTITIES:
- Statement of Cash Flows: period start date, period end date, beginning cash balance, ending cash balance
- Cash Flow Section: type (Operating, Investing, Financing), total amount
- Cash Flow Line Item: description, amount
- Supplemental Disclosure: type (non-cash transaction, interest paid, income tax paid), description, amount

RULES:
- The SCF's ending cash balance must equal the cash balance on the period-end Balance Sheet.
- All cash proceeds from selling a long-term asset must be classified under Investing Activities.
- Gains on the sale of long-term assets must be subtracted from Net Income in the Operating section.
- Losses on the sale of long-term assets must be added to Net Income in the Operating section.
- Cash inflows are positive amounts; cash outflows are negative amounts (or in parentheses).

CALCULATIONS:
- **Net Cash from Operating Activities (Indirect Method)** =
    Net Income
    + Non-cash expenses (e.g., Depreciation, Amortization)
    + Losses on asset sales
    - Gains on asset sales
    + Decreases in current assets (excluding cash)
    - Increases in current assets (excluding cash)
    + Increases in current liabilities (excluding short-term debt)
    - Decreases in current liabilities (excluding short-term debt)
- **Net Cash from Investing Activities** = Sum of cash flows from purchases and sales of noncurrent assets and investments.
- **Net Cash from Financing Activities** = Sum of cash flows from debt issuance/repayment, stock issuance/repurchase, and dividend payments.
- **Net Increase/Decrease in Cash** = Net Cash from Operating + Net Cash from Investing + Net Cash from Financing Activities.
- **Ending Cash Balance** = Beginning Cash Balance + Net Increase/Decrease in Cash.

WORKFLOWS:
- **Generate SCF (Indirect Method):**
    1. Retrieve Net Income for the period.
    2. Calculate adjustments based on non-cash expenses and changes in current asset/liability balances between the start and end of the period.
    3. Sum Net Income and adjustments to get 'Net Cash from Operating Activities'.
    4. Sum cash transactions related to noncurrent assets to get 'Net Cash from Investing Activities'.
    5. Sum cash transactions related to long-term liabilities and equity to get 'Net Cash from Financing Activities'.
    6. Sum the three section totals to calculate 'Net Increase/Decrease in Cash'.
    7. Calculate 'Ending Cash Balance' by adding 'Net Increase/Decrease in Cash' to the 'Beginning Cash Balance'.
    8. Reconcile 'Ending Cash Balance' with the Balance Sheet's cash amount.

CLASSIFICATIONS:
- **Cash Flow Activity Types:**
    - **Operating:** Activities related to net income, current assets (except cash), and current liabilities (except short-term loans).
    - **Investing:** Buying/selling property, plant, equipment, and other long-term investments.
    - **Financing:** Issuing/repaying debt, issuing/repurchasing stock, paying dividends.

REPORTS:
- **Statement of Cash Flows:** Presents cash flows from Operating, Investing, and Financing activities for a specific period, reconciling the beginning and ending cash balances.
- **Notes to Financial Statements (Supplemental Disclosures):**
    - Significant non-cash investing and financing activities.
    - Total cash paid for interest.
    - Total cash paid for income taxes.

STATES:
- (Not specified in the material)





=== SECTION: Financial Analysis & Ratios ===

ENTITIES:
- **Balance Sheet Line Item**: account name, amount, date (point in time)
- **Income Statement Line Item**: account name, amount, period (start date, end date)
- **Cash Flow Statement Line Item**: activity name, amount, period (start date, end date)
- **Corporation Data**: number of common shares outstanding, required preferred stock dividend

RULES:
- Publicly traded corporations must report Earnings Per Share (EPS) on the face of their income statement.
- Published balance sheets must be comparative, showing at least two periods.
- Published income statements and cash flow statements must be comparative, showing at least three periods.

CALCULATIONS:
- **Average Balance Sheet Amount** = (current period end amount + prior period end amount) / 2

**Balance Sheet Based Calculations (Liquidity & Leverage):**
- **Working capital** = current assets – current liabilities
- **Current ratio** = current assets / current liabilities
- **Quick assets** = cash + cash equivalents + temporary investments + accounts receivable
- **Quick (acid test) ratio** = quick assets / current liabilities
- **Total liabilities** = current liabilities + noncurrent liabilities
- **Debt to equity ratio** = total liabilities / total stockholders’ equity
- **Debt to total assets** = total liabilities / total assets

**Income Statement Based Calculations:**
- **Net sales** = gross sales – sales discounts – sales returns – sales allowances
- **Gross profit** = net sales – cost of goods sold
- **Gross margin (%)** = gross profit / net sales
- **Profit margin before tax** = net income before tax / net sales
- **Profit margin after tax** = net income after tax / net sales
- **Earnings available for common stock** = net income after tax – required dividend on preferred stock
- **Earnings per share (EPS, simple)** = net income after tax / number of shares of common stock outstanding
- **Earnings per share (EPS, with preferred stock)** = earnings available for common stock / number of shares of common stock outstanding
- **Net income before interest and tax (EBIT)** = net income after tax + interest expense + income tax expense
- **Times interest earned** = net income before interest and income tax expense / interest expense

**Hybrid (Balance Sheet & Income Statement) Calculations:**
- **Receivables turnover ratio** = net credit sales for the year / average accounts receivable
- **Days’ sales in receivables** = 365 / receivables turnover ratio
- **Inventory turnover ratio** = cost of goods sold for the year / average inventory
- **Days’ sales in inventory** = 365 / inventory turnover ratio
- **Return on stockholders’ equity** = net income after tax / average stockholders’ equity

**Cash Flow Statement Based Calculations:**
- **Free cash flow** = net cash provided by operating activities – capital expenditures
- **Free cash flow (adjusted)** = net cash provided by operating activities – capital expenditures – cash dividends paid

**Vertical Analysis Calculations:**
- **Common-size income statement item (%)** = income statement item amount / net sales
- **Common-size balance sheet item (%)** = balance sheet item amount / total assets

**Additional Ratios Mentioned (Formulas not fully provided in text):**
- Working capital to total assets [Formula not provided]
- Working capital turnover ratio [Formula not provided]
- Fixed assets turnover ratio [Formula not provided]
- Total assets turnover ratio [Formula not provided]
- Equity ratio [Formula not provided]
- Equity turnover ratio [Formula not provided]
- Return on total assets [Formula not provided]
- EBITDA [Formula not provided]
- Book value per share of common stock [Formula not provided]
- Cash flow to debt ratio [Formula not provided]

WORKFLOWS:
- *None specified in the text.*

CLASSIFICATIONS:
- **Ratio Categories**:
    - Liquidity Ratios (e.g., Current Ratio, Quick Ratio)
    - Financial Leverage Ratios (e.g., Debt to Equity)
    - Efficiency Ratios (e.g., Receivables Turnover)
- **Financial Statement Sections**:
    - **Balance Sheet**: Current Assets, Noncurrent Assets, Current Liabilities, Noncurrent Liabilities, Stockholders' Equity
    - **Statement of Cash Flows**: Operating Activities, Investing Activities, Financing Activities

REPORTS:
- **Balance Sheet**: reports assets, liabilities, and equity at a point in time.
- **Income Statement**: reports revenues and expenses over a period of time.
- **Statement of Cash Flows**: reports cash inflows and outflows over a period, categorized by activity.
- **Common-Size Financial Statements**: Presents all line items as a percentage of a base amount (net sales for income statement, total assets for balance sheet).
- **Comparative Financial Statements**: Presents financial statement amounts for the current period alongside amounts from one or more prior periods.
- **Trend Analysis**: Compares financial statement amounts over more than two years (e.g., five years).

STATES:
- *None specified in the text.*





=== SECTION: Bank Reconciliation ===

ENTITIES:
- Bank Reconciliation: date, bank account, unadjusted bank balance, unadjusted book balance, adjusted bank balance, adjusted book balance, status
- Reconciliation Item: type, description, date, amount
- Check: check number, date, payee, amount, status
- Deposit: date, amount, description, status
- General Ledger Cash Account: account identifier, balance
- Bank Statement Line: date, description, amount (debit/credit)

RULES:
- The adjusted balance per bank must equal the adjusted balance per books to complete a reconciliation.
- All items listed under "Adjustments to Books" must be recorded as journal entries in the company's general ledger.
- The company's final General Ledger Cash account balance must equal the adjusted book balance from the reconciliation.
- An independent person should prepare the bank reconciliation.

CALCULATIONS:
- Adjusted Bank Balance = Unadjusted Bank Balance + Deposits in Transit - Outstanding Checks +/- Bank Errors
- Adjusted Book Balance = Unadjusted Book Balance + Credits not in Books (e.g., interest) - Debits not in Books (e.g., fees) +/- Company Errors

WORKFLOWS:
- Preparing a Bank Reconciliation: Compare bank statement to cash ledger → Identify all differences → List adjustments for Bank side → List adjustments for Books side → Verify adjusted balances are equal → Mark reconciliation as complete.
- Posting Book Adjustments: Create journal entry for each "Adjustment to Books" item → Post journal entries → Verify GL Cash account balance matches the reconciled adjusted balance.

CLASSIFICATIONS:
- Adjustments to Bank Balance:
  - Additions: Deposits in Transit, Bank Errors
  - Subtractions: Outstanding Checks, Bank Errors
- Adjustments to Book Balance:
  - Additions: Interest Earned, Bank Credit Memos (e.g., notes collected), Company Errors
  - Subtractions: Bank Fees, NSF Checks (Return Items), Bank Debit Memos, Company Errors

REPORTS:
- Bank Reconciliation Report: Shows unadjusted bank balance, unadjusted book balance, all reconciling items for both sides, and the final equal adjusted balances for a specific period.
- Balance Sheet: Reports the final adjusted cash balance.

STATES:
- Bank Reconciliation: In Progress → Reconciled
- Check: Issued → Outstanding → Cleared / Voided
- Deposit: Recorded → In Transit → Cleared




=== SECTION: Core Entities ===

ENTITIES:
- Customer: name, contact info
- Sale/Invoice: customer, date, line items, credit terms, total amount, shipping terms (FOB Shipping Point, FOB Destination)
- Invoice Line: item, quantity, price
- Journal Entry: date, description, status
- Journal Line: account, debit amount, credit amount
- Customer Payment: customer, date, amount received, associated invoice(s)
- Chart of Accounts: account number, account name, account type
- Account: current balance

=== SECTION: Rules & Validations ===

RULES:
- Sales transactions must be recorded when ownership of goods is transferred.
- A write-off of a specific account receivable does not affect the Bad Debts Expense account under the allowance method.
- A write-off of a specific account receivable does not change the Net Realizable Value of Accounts Receivable.
- The balance in Allowance for Doubtful Accounts must be a credit or zero.
- For financial reporting, the allowance method must be used.
- For US income tax reporting, the direct write-off method must be used.
- Temporary accounts (e.g., Bad Debts Expense) must be closed to zero at the end of an accounting year.
- Permanent accounts (e.g., Allowance for Doubtful Accounts) carry their balance forward to the next accounting year.

=== SECTION: Calculations ===

CALCULATIONS:
- Net Receivable = Gross Sale Amount - Sales Returns
- Sales Discount Amount = Net Receivable * Discount Percentage
- Net Realizable Value of AR = Accounts Receivable Balance - Allowance for Doubtful Accounts Balance
- Bad Debts Expense (Percent of Sales Method) = Credit Sales for the Period * Historical Bad Debt Percentage
- Required Allowance Balance (Aging Method) = Sum of (Total AR in each age bucket * Uncollectible % for that bucket)
- Interest on Past Due AR = Past Due Balance * Periodic Interest Rate
- Accounts Receivable Turnover Ratio [?]
- Days Sales in Accounts Receivable [?]

=== SECTION: Workflows ===

WORKFLOWS:
- Sale on Credit (Services): Debit Accounts Receivable → Credit Service Revenues
- Sale on Credit (Goods): Debit Accounts Receivable, Credit Sales → Debit Cost of Goods Sold, Credit Inventory
- Handling Freight Costs (FOB Destination): Debit Freight-Out Expense → Credit Cash/Accounts Payable
- Customer Returns Goods: Debit Sales Returns, Credit Accounts Receivable → Debit Inventory, Credit Cost of Goods Sold
- Customer Pays Within Discount Period: Debit Cash, Debit Sales Discounts → Credit Accounts Receivable
- Customer Pays After Discount Period: Debit Cash → Credit Accounts Receivable
- Establishing Bad Debt Allowance (Period-End): Calculate required allowance balance → Debit Bad Debts Expense, Credit Allowance for Doubtful Accounts for the adjustment amount needed
- Writing Off an Uncollectible Account (Allowance Method): Debit Allowance for Doubtful Accounts → Credit Accounts Receivable
- Recovering a Written-Off Account (Allowance Method): Debit Accounts Receivable, Credit Allowance for Doubtful Accounts → Debit Cash, Credit Accounts Receivable
- Writing Off an Uncollectible Account (Direct Method): Debit Bad Debts Expense → Credit Accounts Receivable

=== SECTION: Classifications ===

CLASSIFICATIONS:
- Accounts Receivable: Current Asset
- Allowance for Doubtful Accounts: Contra Asset
- Bad Debts Expense: Expense
- Sales Discounts: Contra Revenue
- Freight-Out Expense: Selling Expense
- Accounts Receivable Aging Buckets: Current, 1-30 Days Past Due, 31-60 Days Past Due, etc.

=== SECTION: Reports ===

REPORTS:
- Aging of Accounts Receivable: Lists each customer's unpaid invoices, sorted into age buckets (Current, 1-30 days past due, etc.). Shows total amount receivable per bucket.
- Customer Statement: Itemized list of transactions (invoices, payments, returns) for a customer over a period, showing the outstanding balance.
- Balance Sheet: Reports Accounts Receivable and Allowance for Doubtful Accounts to show Net Realizable Value.
- Income Statement: Reports Sales Revenue, Sales Discounts, Cost of Goods Sold, and Bad Debts Expense.

=== SECTION: States ===

STATES:
- Accounts Receivable: Unpaid → Paid
- Uncollectible Account: Identified as uncollectible → Written-off → Recovered
- [?] Receivable Status: Normal → Pledged → Sold (factored)

NOTES:
- The system must support two distinct methods for handling bad debt: the Allowance Method (for financial statements) and the Direct Write-off Method (for tax purposes).
- The Allowance Method itself has two approaches for estimating the expense: Percentage of Sales and Aging of Accounts Receivable.
- Need to track receivables sold "with recourse", as this creates a contingent liability.





=== SECTION: Accounts Payable ===

ENTITIES:
- **Vendor Invoice:** vendor, invoice number, invoice date, amount, terms, due date, status
- **Purchase Order (PO):** PO number, date, vendor, items (description, quantity, unit price)
- **Receiving Report:** date received, items (description, quantity received)
- **Voucher:** cover sheet for attaching related documents (PO, Receiving Report, Invoice), approval status, GL distribution
- **Vendor:** name, contact information
- **Payment:** payment date, payment reference, amount paid, vendor, associated invoice(s)
- **Accrued Liability:** amount, period, description, related expense/asset account

RULES:
- An invoice must be approved before it can be scheduled for payment.
- Approval for invoices with a PO requires a three-way match: invoice details must match the purchase order and receiving report (item, quantity, price).
- Processed invoices/vouchers must be marked to prevent duplicate payment.
- Pay only from vendor invoices, not from vendor statements.
- All expenses and liabilities must be recorded in the period they are incurred.
- Costs for long-term items are recorded as assets; costs with no future value are expensed immediately.
- Costs paid in advance are recorded as prepaid assets.

CALCULATIONS:
- **Accounts Payable Balance** = Sum of all unpaid, approved vendor invoices
- **Net Amount Owed** = Invoice Amount - Returns/Allowances
- **Early Payment Discount** = Net Amount Owed * Discount Percentage
- **Payment Amount (with discount)** = Net Amount Owed - Early Payment Discount

WORKFLOWS:
- **Invoice Processing:** Receive Invoice → Match to PO & Receiving Report (if applicable) → Verify & Approve → Record Liability (Credit AP, Debit Expense/Asset) → Schedule Payment
- **Payment Processing:** Select Invoices Due → Generate Payment → Record Payment (Debit AP, Credit Cash) → Mark Invoice as Paid
- **End-of-Period Accrual:** Identify incurred but unrecorded expenses → Create adjusting entry (Debit Expense/Asset, Credit Accrued Liabilities) → Reverse entry in the next period

CLASSIFICATIONS:
- **Liabilities:**
    - Current Liabilities: Accounts Payable, Accrued Liabilities
- **Assets:**
    - Current Assets: Prepaid Expenses
    - Fixed Assets: Equipment, Vehicles
- **Expenses:**
    - Operating Expenses: Repairs & Maintenance Expense, Rent Expense

REPORTS:
- **AP Aging:** Unpaid invoices grouped by how long they are outstanding (e.g., Current, 30 days, 60 days).
- **AP Distribution:** Summary of which expense/asset accounts were debited for a set of invoices.
- **Balance Sheet:** Reports Accounts Payable and Accrued Liabilities under Current Liabilities.
- **Income Statement:** Reports expenses related to vendor invoices.

STATES:
- **Vendor Invoice:** Pending Approval → Approved / Unpaid → Paid

NOTES:
- System must calculate due dates and discount eligibility based on invoice terms (e.g., Net 30, 2/10, n/30).
- Need to track payments to individuals to distinguish between employees (W-2) and independent contractors (1099). [?]
- Need to handle sales and use tax. [?]
- Need to handle travel and entertainment (T&E) expense compliance. [?]







=== SECTION: Core Inventory & COGS ===

ENTITIES:
- Inventory Item: SKU/identifier, description, quantity on hand, unit cost
- Inventory Layer: SKU/identifier, purchase date, quantity purchased, cost per unit (for FIFO/LIFO tracking)
- Purchase Transaction: supplier, date, item, quantity, cost, freight costs
- Sales Transaction: customer, date, item, quantity, sale price
- General Ledger Account: account number, name, type (Asset, Liability, etc.), balance
- Journal Entry: date, description, status
- Journal Line: account, debit amount, credit amount

RULES:
- Inventory cost must include all costs to get goods ready for sale (e.g., purchase price + freight).
- The cost flow assumption (e.g., LIFO) does not need to match the physical flow of goods.
- A physical inventory count must be performed at least once a year.
- Discrepancies between system records and physical counts require an adjusting journal entry.
- Under the perpetual system, every sale must generate two entries: one for revenue and one for COGS/Inventory reduction.
- The 'Purchases' account is only used in the Periodic system.
- Perpetual FIFO and Periodic FIFO calculations result in the same COGS and Ending Inventory values.
- Perpetual LIFO and Periodic LIFO calculations result in different COGS and Ending Inventory values.

CALCULATIONS:
- Cost of Goods Available for Sale = Beginning Inventory Cost + Net Purchases Cost
- Gross Profit = Sales - Cost of Goods Sold
- Inventory Turnover Ratio = Cost of Goods Sold / Average Inventory
- Days' Sales in Inventory = (Ending Inventory / Cost of Goods Sold) * number of days in period

WORKFLOWS:
- Purchase (Perpetual System): Debit Inventory, Credit Accounts Payable/Cash
- Sale (Perpetual System):
    1. Record Revenue: Debit Accounts Receivable/Cash, Credit Sales
    2. Record COGS: Debit Cost of Goods Sold, Credit Inventory
- Purchase (Periodic System): Debit Purchases, Credit Accounts Payable/Cash
- Sale (Periodic System): Debit Accounts Receivable/Cash, Credit Sales (No COGS entry at time of sale)
- End-of-Period (Periodic System):
    1. Calculate Ending Inventory cost based on physical count and cost flow assumption.
    2. Adjust the Inventory general ledger account to this balance.
    3. Calculate and record Cost of Goods Sold for the period.
- Physical Inventory Adjustment:
    1. Perform physical count of inventory.
    2. Compare physical count to system quantity.
    3. Create adjusting journal entry for the value of the discrepancy (e.g., Debit COGS/Inventory Shrinkage, Credit Inventory).

CLASSIFICATIONS:
- Asset: Inventory (Current Asset)
- Expense: Cost of Goods Sold, Purchases (used only in Periodic system)
- Revenue: Sales

REPORTS:
- Balance Sheet: Reports value of Ending Inventory as a Current Asset.
- Income Statement: Reports Sales, Cost of Goods Sold, and Gross Profit for a period.

---

=== SECTION: Cost Flow Assumptions ===

RULES:
- The system must support a choice of cost flow assumption (FIFO, LIFO, Average, Specific ID) and inventory system (Perpetual, Periodic).

CALCULATIONS:
- **FIFO (First-In, First-Out)**
    - COGS = Cost of the oldest inventory units held.
    - Ending Inventory = Cost of the most recently acquired units.
- **LIFO (Last-In, First-Out)**
    - Periodic LIFO: COGS = Cost of the last units purchased *within the period*, regardless of sale date.
    - Perpetual LIFO: COGS = Cost of the last units purchased *at the time of the sale*.
    - Ending Inventory = Cost of the oldest units held.
- **Weighted-Average**
    - Periodic Average Cost = Total Cost of Goods Available for Sale / Total Units Available for Sale.
    - COGS (Periodic) = Units Sold * Periodic Average Cost.
- **Moving-Average (Perpetual Average)**
    - New Average Cost (calculated after each purchase) = Total cost of inventory on hand / Total units on hand.
    - COGS (Perpetual) = Units sold * New Average Cost at the time of sale.
- **Specific Identification**
    - COGS = The actual cost of the specific, identified unit that was sold.
    - Ending Inventory = The sum of the actual costs of all specific units remaining.

---

=== SECTION: Inventory Estimation Methods ===

RULES:
- These methods are used for interim reporting or loss calculation when a physical count is not feasible.

CALCULATIONS:
- **Gross Profit Method**
    1. Historical COGS % = 1 - (Historical Gross Profit / Historical Sales)
    2. Estimated COGS = Current Period Sales * Historical COGS %
    3. Estimated Ending Inventory = Cost of Goods Available for Sale - Estimated COGS
- **Retail Method**
    1. Cost-to-Retail Ratio = Goods Available for Sale at Cost / Goods Available for Sale at Retail
    2. Ending Inventory at Retail = Goods Available for Sale at Retail - Sales
    3. Estimated Ending Inventory at Cost = Ending Inventory at Retail * Cost-to-Retail Ratio

NOTES:
- The text mentions "dollar value LIFO" as an advanced method for gaining LIFO benefits without unit tracking, potentially using price indexes. This could be considered a future, advanced feature. [?]





=== SECTION: Depreciation ===

ENTITIES:
- **Depreciable Asset:** cost, purchase_date, in_service_date, estimated_useful_life (in years or units), estimated_salvage_value, depreciation_method, asset_type (manufacturing vs. non-manufacturing)
- **Accumulated Depreciation:** linked_asset, current_balance
- **Journal Entry:** date, description
- **Journal Line:** account, debit_amount, credit_amount

RULES:
- Total depreciation cannot exceed the asset's depreciable cost (cost - salvage value).
- Depreciation stops once the asset's book value equals its salvage value.
- For the Double-Declining-Balance method, depreciation must stop when book value reaches salvage value, even if the calculation would go lower.
- Changes in estimates (useful life, salvage value) only affect current and future depreciation calculations, not past periods.
- Expenditures that maintain an asset are expensed immediately (Repairs & Maintenance).
- Expenditures that improve or expand an asset are capitalized (added to the asset's cost) and depreciated over the remaining life.

CALCULATIONS:
- **Depreciable Cost** = Asset Cost - Estimated Salvage Value
- **Book Value** = Asset Cost - Accumulated Depreciation
- **Straight-Line (Annual)** = Depreciable Cost / Useful Life in Years
- **Units-of-Activity Rate** = Depreciable Cost / Total Estimated Units of Life
- **Units-of-Activity Expense (Period)** = Units-of-Activity Rate * Units in Period
- **Double-Declining-Balance Rate** = (1 / Useful Life in Years) * 2
- **Double-Declining-Balance Expense (Period)** = Book Value at Start of Period * DDB Rate
- **Sum-of-the-Years'-Digits Denominator** = n(n+1)/2, where n = useful life in years
- **Sum-of-the-Years'-Digits Expense (Period)** = (Remaining Years of Life / SYD Denominator) * Depreciable Cost
- **Gain/Loss on Sale** = Sale Price - Book Value at Date of Sale
- **Depreciation on Change of Estimate** = (Current Book Value - Revised Salvage Value) / Remaining Useful Life

WORKFLOWS:
- **Record Periodic Depreciation:** Calculate period expense → Create Journal Entry (Debit Depreciation Expense, Credit Accumulated Depreciation) → Post Entry.
- **Sell an Asset:** Update depreciation to date of sale → Calculate book value → Record sale entry (Debit Cash, Debit Accumulated Depreciation; Credit Asset, Credit Gain or Debit Loss) → Remove asset from service.
- **Change an Estimate:** Calculate book value at date of change → Use (Book Value - New Salvage Value) / Remaining Life for all future depreciation calculations.

CLASSIFICATIONS:
- **Asset Categories:** Property, Plant, and Equipment (e.g., Buildings, Machinery, Vehicles, Fixtures)
- **Contra-Asset Accounts:** Accumulated Depreciation
- **Expense Accounts:** Depreciation Expense, Loss on Sale of Asset
- **Gain Accounts:** Gain on Sale of Asset
- **Asset Cost Allocation:**
    - **Manufacturing Assets:** Depreciation is part of Manufacturing Overhead (a product cost).
    - **Non-Manufacturing Assets:** Depreciation is an operating expense (a period cost).

REPORTS:
- **Balance Sheet:** Shows Asset Cost, less Accumulated Depreciation, equals net Book Value.
- **Income Statement:** Shows Depreciation Expense, and any Gain or Loss on Sale of Asset.

STATES:
- **Asset:** In Service → Fully Depreciated → Disposed

NOTES:
- Depreciation must be prorated for partial periods (e.g., an asset put in service on July 1 gets 6 months of depreciation in the first calendar year).
- The system may need to support switching from DDB to Straight-Line in later years to ensure the asset fully depreciates to its salvage value.
- Asset Impairment is a related concept but its calculation logic is not detailed in the source material.





=== SECTION: PAYROLL ===

ENTITIES:
- Employee: classification (Employee, Independent Contractor), exempt status (Exempt, Non-exempt), pay type (Salary, Hourly), pay rate, W-4 info (filing status, allowances)
- Pay Period: start date, end date, pay date, frequency (weekly, biweekly, semimonthly)
- Payroll Run: pay period, employee, hours worked, gross pay, list of withholdings, list of employer contributions, net pay
- Withholding/Deduction: type (FICA, FIT, SIT, Garnishment, 401k, Insurance), amount, pre-tax/post-tax status
- Employer Contribution: type (FICA, FUTA, SUTA, Worker's Comp, 401k Match, Insurance), amount
- Liability Account: type (Wages Payable, FICA Tax Payable, FIT Payable, SUTA Payable, Vacation Payable), balance

RULES:
- Payroll expenses must be accrued and reported in the period they are incurred, not when paid.
- An accrual adjusting entry is required if a pay period crosses the end of a financial reporting period.
- Independent contractors paid $600+ in a year must be issued a Form 1099-NEC, unless they are a corporation.
- Non-exempt employees must be paid overtime for hours worked over 40 in a workweek.
- FICA (Social Security) tax has an annual wage base limit for both employee and employer.
- Medicare tax has no wage limit.
- The employer does not match the employee's Additional Medicare Tax.
- FUTA tax is paid only by the employer.
- SUTA tax is typically paid only by the employer.
- Federal payroll tax deposits must be made via Electronic Funds Transfer (EFTPS).
- Tax deposit frequency (monthly, semi-weekly, next-day) is determined by the total tax liability amount.
- The cost of paid time off (e.g., vacation) must be accrued as a liability as the employee earns it.

CALCULATIONS:
- Gross Pay (Hourly) = Hours Worked * Hourly Rate + Overtime Hours * Overtime Rate
- Gross Pay (Salaried) = Annual Salary / Number of Pay Periods in Year
- Net Pay = Gross Pay - Total Employee Withholdings
- Overtime Rate = Regular Rate * 1.5
- Salaried Employee Hourly Rate (for OT calculation) = Annual Salary / 2080
- Employee Social Security Tax = 6.2% * Gross Pay (up to annual wage limit)
- Employee Medicare Tax = 1.45% * Gross Pay
- Additional Medicare Tax (Employee) = 0.9% * Gross Pay (on wages over $200,000)
- Employer Social Security Tax = Matches employee's calculated amount
- Employer Medicare Tax = Matches employee's calculated amount (excluding Additional Medicare Tax)
- SUTA Tax = SUTA Rate * Gross Pay (up to state wage base limit)
- FUTA Tax = FUTA Rate * Gross Pay (up to federal wage base limit of $7,000)

WORKFLOWS:
- Process Payroll Run:
  1. Calculate gross pay for each employee.
  2. Calculate all employee withholdings and deductions.
  3. Calculate all employer contributions/taxes.
  4. Calculate net pay.
  5. Generate payroll journal entries (one for employee pay, one for employer taxes).
  6. Generate paychecks or direct deposits.
- Record Payroll Expense Journal Entry:
  1. Debit Wage/Salary Expense.
  2. Debit PTO Liability (if PTO was taken).
  3. Credit all withholding liability accounts (FICA Payable, FIT Payable, etc.).
  4. Credit Wages Payable for total net pay.
- Record Employer Tax Expense Journal Entry:
  1. Debit Payroll Tax Expense.
  2. Credit employer tax liability accounts (FICA Payable, FUTA Payable, SUTA Payable).
- Pay Employees:
  1. Debit Wages Payable.
  2. Credit Cash.
- Remit Taxes:
  1. Debit all tax liability accounts (FICA Payable, FIT Payable, etc.).
  2. Credit Cash.
- Accrue Paid Time Off:
  1. Debit Paid Time Off Expense.
  2. Credit Paid Time Off Liability.
- File Quarterly Taxes:
  1. Aggregate payroll data for the quarter.
  2. Populate and file Form 941.

CLASSIFICATIONS:
- Worker Type: Employee, Independent Contractor, Proprietor/Partner
- Pay Type: Salary, Wages, Bonus, Commission
- Employee Exemption Status: Exempt, Non-exempt (from overtime)
- Deduction Type: Pre-Tax, Post-Tax

REPORTS:
- Form W-2 (Wage and Tax Statement): Annual report for each employee showing total wages and taxes withheld.
- Form W-3 (Transmittal of Wage and Tax Statements): Annual summary of all W-2s filed by an employer.
- Form 941 (Employer's Quarterly Federal Tax Return): Quarterly report of wages paid and total payroll taxes.
- Form 940 (Employer's Annual Federal Unemployment Tax Return): Annual FUTA report.
- Form 1099-NEC: Annual report for nonemployee compensation.
- Payroll Summary: Internal report showing gross pay, deductions, and net pay by employee and/or department for a pay period.

STATES:
- [None explicitly mentioned in the text]

NOTES:
- The system must handle different tax rates and wage base limits for Federal, State, Social Security, SUTA, and FUTA, and these values change annually.
- Worker's Compensation insurance rates can vary by employee job role within the same company.






=== SECTION: Bonds Payable ===

ENTITIES:
- Bond: face amount, stated interest rate, maturity date, interest payment dates, issue date, issue price
- Premium on Bonds Payable Account: initial amount, unamortized balance (linked to a bond)
- Discount on Bonds Payable Account: initial amount, unamortized balance (linked to a bond)
- Bond Issue Costs: amount, unamortized balance (linked to a bond)

RULES:
- If a bond's issue price is greater than its face value, a Premium is recorded.
- If a bond's issue price is less than its face value, a Discount is recorded.
- The balance in the Premium or Discount account must be amortized over the life of the bond.
- At maturity, the book value of the bond must equal its face value (unamortized premium/discount must be zero).
- When a bond is issued between interest dates, the issuer collects accrued interest from the investor.

CALCULATIONS:
- Periodic Cash Interest Payment = Face Amount * Stated Interest Rate * (Time Period / 12)
- Bond Book (Carrying) Value = Face Value + Unamortized Premium - Unamortized Discount - Unamortized Issue Costs
- Straight-Line Amortization Amount = Total Premium or Discount / Total Number of Periods in Bond Life
- Effective Interest Method - Interest Expense = Bond Book Value at start of period * Market Rate per period
- Effective Interest Method - Premium Amortization = Cash Interest Paid - Interest Expense
- Effective Interest Method - Discount Amortization = Interest Expense - Cash Interest Paid
- Bond Issue Price (Present Value) = Present Value of Principal + Present Value of all future Interest Payments (discounted at the market rate)

WORKFLOWS:
- Issuing a Bond: Record cash received → Record Bonds Payable at face value → Record Premium or Discount as the difference → Record any accrued interest received as Interest Payable.
- Recording a Periodic Interest Payment: Calculate amortization for the period → Calculate interest expense → Record cash payment → Update book value of the bond.
- Bond Maturity: Make final interest payment and record final amortization → Pay principal (face value) to bondholders → Zero out the Bonds Payable liability.

CLASSIFICATIONS:
- Account Categories:
    - Long-Term Liabilities: Bonds Payable, Premium on Bonds Payable (adjunct liability), Discount on Bonds Payable (contra liability)
    - Current Liabilities: Interest Payable
    - Expenses: Interest Expense
- Bond Types:
    - Term vs. Serial
    - Secured vs. Unsecured (Debenture)
    - Convertible
    - Callable

REPORTS:
- Balance Sheet: Shows Bonds Payable, netted with unamortized Discount, added to unamortized Premium, and reduced by unamortized Bond Issue Costs to present the bond's net carrying value.
- Income Statement: Shows Interest Expense for the period (includes amortization of premium/discount/issue costs).

STATES:
- Bond: Issued/Outstanding → Matured/Retired

NOTES:
- The effective interest rate method is the preferred amortization method.
- Bond Issue Costs are treated as a direct deduction from the carrying amount of the Bonds Payable liability.






=== SECTION: Stockholders' Equity ===

### ENTITIES & THEIR PROPERTIES
-   **Stockholders' Equity**: The main equity section of the balance sheet.
-   **Common Stock**: par_value, number_of_authorized_shares, number_of_issued_shares.
-   **Preferred Stock**: par_value, dividend_rate, number_of_shares, features (cumulative, participating, callable, convertible).
-   **Paid-in Capital in Excess of Par Value**: amount (separate for common and preferred).
-   **Retained Earnings**: current_balance.
-   **Accumulated Other Comprehensive Income (AOCI)**: current_balance.
-   **Treasury Stock**: number_of_shares, acquisition_cost (this is a contra-equity account).
-   **Paid-in Capital from Treasury Stock**: current_balance.
-   **Dividends Payable**: amount (a current liability, not an equity account).
-   **Common Stock Dividend Distributable**: amount (temporary equity account).

### RULES
-   Outstanding Shares = Issued Shares - Treasury Shares.
-   Issued Shares must be less than or equal to Authorized Shares.
-   Gains or losses on treasury stock transactions must not be reported on the income statement; they are recorded directly in equity accounts.
-   Cash dividends can only be declared if there is a positive (credit) balance in Retained Earnings.
-   Dividends are paid only on outstanding shares (not treasury shares).
-   Preferred stock dividends must be paid before common stock dividends.
-   For cumulative preferred stock, any dividends in arrears (unpaid past dividends) must be paid before common dividends can be paid.
-   Dividends in arrears are not a liability until declared but must be disclosed in financial statement notes.
-   Stock issued for non-cash items must be recorded at the fair market value of the stock or the item received, whichever is more clearly determinable.
-   Prior period adjustments for significant errors directly adjust the beginning balance of Retained Earnings.

### CALCULATIONS
-   **Retained Earnings Balance** = Beginning Balance + Net Income (- Net Loss) - Dividends Declared.
-   **Book Value of Corporation** = Total Stockholders' Equity.
-   **Book Value per Share of Preferred Stock** = Call Price + Dividends in Arrears.
-   **Total Book Value of Common Stock** = Total Stockholders' Equity - (Book Value per Share of Preferred * Number of Preferred Shares Outstanding).
-   **Book Value per Share of Common Stock** = Total Book Value of Common Stock / Number of Common Shares Outstanding.
-   **Earnings Per Share (EPS)** = (Net Income - Preferred Dividends) / Weighted-Average Number of Common Shares Outstanding.
-   **Weighted-Average Common Shares** = Sum of (Shares Outstanding * Fraction of year they were outstanding).

### WORKFLOWS
-   **Issuing Stock**: Debit Cash → Credit Stock Account (at par) → Credit Paid-in Capital in Excess of Par (for remainder).
-   **Purchasing Treasury Stock**: Debit Treasury Stock (at acquisition cost) → Credit Cash.
-   **Selling Treasury Stock**: Debit Cash → Credit Treasury Stock (at original cost). The difference is recorded in `Paid-in Capital from Treasury Stock` (for a "gain") or debited to `Paid-in Capital from Treasury Stock` and then `Retained Earnings` (for a "loss").
-   **Cash Dividend**: Declaration Date (Debit Retained Earnings, Credit Dividends Payable) → Record Date (No entry) → Payment Date (Debit Dividends Payable, Credit Cash).
-   **Small Stock Dividend (<20-25%)**: Debit Retained Earnings for the *market value* of shares to be issued.
-   **Large Stock Dividend (>20-25%)**: Debit Retained Earnings for the *par value* of shares to be issued.
-   **Stock Split**: Increase number of shares → Decrease par value per share proportionally → No change to account balances.
-   **Appropriating Retained Earnings**: Debit Retained Earnings → Credit Appropriated Retained Earnings.

### CLASSIFICATIONS
-   **Stockholders' Equity Components**:
    -   Paid-in Capital (Contributed Capital)
    -   Retained Earnings (or Accumulated Deficit)
    -   Accumulated Other Comprehensive Income
    -   Less: Treasury Stock
-   **Share Status**:
    -   Authorized
    -   Issued
    -   Outstanding
-   **Stock Types**:
    -   Common Stock
    -   Preferred Stock

### REPORTS
-   **Balance Sheet**: Details all components of Stockholders' Equity at a point in time.
-   **Statement of Stockholders' Equity**: Shows the beginning balance, changes during the period, and ending balance for each component of equity.
-   **Income Statement**: Must display Earnings Per Share (EPS) for publicly-traded companies.

### STATES
-   **Retained Earnings**: Normal (credit balance) ↔ Deficit (debit balance).
-   **Cash/Stock Dividend**: Declared → Payable/Distributable → Paid/Distributed.
-   **Retained Earnings Appropriation**: Unappropriated ↔ Appropriated/Restricted.






=== SECTION: Present Value Engine ===

ENTITIES:
- PV/FV Calculation: present_value, future_value, interest_rate, number_of_periods, compounding_frequency

RULES:
- A PV/FV calculation must have exactly three of the four main variables (PV, FV, i, n) defined to solve for the fourth.
- The interest rate (`i`) and number of periods (`n`) must be adjusted to match the compounding frequency for all calculations.

CALCULATIONS:
- Present Value = Future Value / (1 + periodic interest rate) ^ number of periods
- Periodic Interest Rate = Annual Interest Rate / number of compounding periods per year
- Number of Periods = Number of Years * number of compounding periods per year

WORKFLOWS:
- Calculate Unknown Variable:
  1. Receive three of four variables (PV, FV, i, n) and compounding frequency.
  2. Convert annual rate and years to periodic rate (`i`) and total periods (`n`).
  3. Solve for the single unknown variable using the PV formula.

CLASSIFICATIONS:
- Compounding Frequency: Annually, Semiannually, Quarterly, Monthly

---

=== SECTION: Notes Receivable ===

ENTITIES:
- Note Receivable: face_value, issue_date, due_date, imputed_interest_rate, present_value_at_issuance, carrying_value
- Amortization Schedule Line: period, beginning_carrying_value, interest_revenue, discount_amortized, ending_carrying_value

RULES:
- A non-interest-bearing note must be recorded at its present value.
- The difference between face value and present value is recorded as a discount.
- The discount must be amortized to interest revenue over the life of the note.
- The carrying value of the note cannot exceed its face value.

CALCULATIONS:
- Initial Discount = Face Value - Present Value
- Carrying Value = Face Value - Unamortized Discount
- Interest Revenue (Effective Interest Method) = Carrying Value at beginning of period * Effective Interest Rate per period
- Discount Amortized (per period) = Calculated Interest Revenue

WORKFLOWS:
- Record a Non-Interest-Bearing Note:
  1. Calculate the note's Present Value based on its face value, term, and an imputed interest rate.
  2. Calculate the Initial Discount.
  3. Generate Journal Entry: Debit `Notes Receivable` (face value), Credit `Revenue` (present value), Credit `Discount on Notes Receivable` (discount amount).
- Amortize Discount (per period):
  1. Calculate interest revenue using the effective interest method.
  2. Generate Journal Entry: Debit `Discount on Notes Receivable`, Credit `Interest Revenue`.
  3. Update the note's carrying value.
- Collect Matured Note:
  1. Verify the discount is fully amortized.
  2. Generate Journal Entry: Debit `Cash`, Credit `Notes Receivable` for the face value.

CLASSIFICATIONS:
- Account Types:
  - Asset: Notes Receivable
  - Contra-Asset: Discount on Notes Receivable
  - Revenue: Interest Revenue

REPORTS:
- Amortization Schedule: Shows the periodic amortization of the discount and the change in the note's carrying value over its life.
- Balance Sheet: Reports Notes Receivable at its net carrying value.
- Income Statement: Reports Interest Revenue earned for the period.

STATES:
- Note Receivable: Outstanding → Matured → Collected

NOTES:
- The system should support both the Effective Interest Rate method and the Straight-Line method for amortizing the discount. The definition of when to use Straight-Line ("insignificant") is a user policy decision.





=== SECTION: Present Value of an Ordinary Annuity ===

ENTITIES:
- **Loan / Note Receivable**: Present Value (initial principal), Face Value (total payments), Payment Amount (PMT), Interest Rate per Period (i), Number of Periods (n), Payment Frequency (e.g., monthly, quarterly, annual)
- **Amortization Schedule**: a collection of Amortization Schedule Lines
- **Amortization Schedule Line**: Period Number, Beginning Balance, Payment Amount, Interest Portion, Principal Portion, Ending Balance
- **Journal Entry**: date, description, status
- **Journal Line**: account, debit, credit

RULES:
- A non-interest-bearing note received for services/goods must be recorded at its present value.
- The difference between the face value and present value of a note is recorded as a "Discount on Notes Receivable".
- Discount on Notes Receivable must be amortized to Interest Revenue over the life of the note.
- The effective interest rate method is required for amortization if the amount is material.
- The straight-line method may be used for amortization if the amount is immaterial.

CALCULATIONS:
- **Present Value of Ordinary Annuity (PVOA)** = Payment Amount * PVOA Factor(i, n)
- **Total Discount** = (Payment Amount * Number of Periods) - Present Value
- **Interest Revenue (Effective Rate Method)** = Carrying Value (Beginning Balance) * Interest Rate per Period
- **Principal Reduction** = Payment Amount - Interest Revenue
- **Carrying Value (Book Value) of Note** = Notes Receivable (Face Value) - Unamortized Discount
- **Straight-Line Amortization per Period** = Total Discount / Number of Periods

WORKFLOWS:
- **Recording a Non-Interest-Bearing Note:**
  1. Calculate the Present Value (PVOA) of the future payments.
  2. Calculate the Total Discount.
  3. Create a journal entry: Debit Notes Receivable (Face Value), Credit Discount on Notes Receivable (contra-asset), Credit Revenue (PVOA).

- **Periodic Amortization & Payment Receipt (Effective Rate Method):**
  1. Calculate Interest Revenue for the period.
  2. Create journal entry to amortize discount: Debit Discount on Notes Receivable, Credit Interest Revenue.
  3. Create journal entry for cash receipt: Debit Cash, Credit Notes Receivable.
  4. Update the Amortization Schedule.
  5. Repeat for all periods.

CLASSIFICATIONS:
- **Assets**: Notes Receivable
- **Contra-Assets**: Discount on Notes Receivable
- **Revenues**: Service Revenue, Interest Revenue

REPORTS:
- **Loan/Note Amortization Schedule**: Shows the breakdown of each payment into interest and principal, and the remaining balance for each period.
- **Balance Sheet**: Shows the carrying value of the Notes Receivable (Face Value - Unamortized Discount).
- **Income Statement**: Shows the Interest Revenue recognized for the period.

STATES:
- **Note Receivable**: Active → Paid Off






=== SECTION: Future Value Calculations ===

ENTITIES:
- `Financial Calculation`: present_value (PV), future_value (FV), annual_interest_rate, compounding_frequency, term_duration
- `Cash Flow`: amount, date
- `Cash Flow Series`: a collection of `Cash Flow` entities, target_future_date, annual_interest_rate, compounding_frequency

RULES:
- A calculation requires all variables to be known except for one, which will be calculated.
- The interest rate per period (`i`) and total number of periods (`n`) must be derived from the annual rate, term, and compounding frequency.
- Input values (PV, FV, rate, term) must be positive.

CALCULATIONS:
- `Interest Rate per Period (i)` = annual_interest_rate / number_of_compounding_periods_per_year
- `Total Number of Periods (n)` = term_duration_in_years * number_of_compounding_periods_per_year
- `Future Value (FV)` = PV * (1 + i)^n
- `Present Value (PV)` = FV / (1 + i)^n
- `Number of Periods (n)` = log(FV / PV) / log(1 + i)
- `Interest Rate per Period (i)` = (FV / PV)^(1/n) - 1
- `Future Value of a Series` = Sum of the future values of each individual cash flow
- `Rule of 72 (Years to Double)` = 72 / annual_interest_rate_as_percent
- `Rule of 72 (Rate to Double)` = 72 / term_duration_in_years

WORKFLOWS:
- `Solve for Unknown Variable`:
    1. Receive all known variables (PV, FV, rate, term, frequency).
    2. Determine period rate (`i`) and total periods (`n`).
    3. Apply the correct formula to calculate the single unknown variable.
    4. Convert `n` or `i` back to years or an annual rate if they were the unknown.
- `Calculate FV of a Cash Flow Series`:
    1. For each cash flow, determine the number of periods (`n`) between its date and the target future date.
    2. Calculate the FV for each individual cash flow.
    3. Sum all calculated FVs.

CLASSIFICATIONS:
- `Compounding Frequency`: Annually (1/yr), Semiannually (2/yr), Quarterly (4/yr), Monthly (12/yr)

REPORTS:
- `Calculation Summary`: Displays all inputs and the calculated result for a single calculation.
- `Investment Growth Schedule`: A period-by-period table showing beginning balance, interest earned, and ending balance.

STATES:
- N/A

NOTES:
- The "Rule of 72" provides an estimate and should be presented as such. It assumes annual compounding.






=== SECTION: Core Accounting & General Ledger ===

ENTITIES:
- Chart of Accounts: account number, name, type (Asset, Liability, Net Asset, Revenue, Expense)
- Journal Entry: date, description, status
- Journal Line: account, debit amount, credit amount, functional classification tag, program tag [?]

RULES:
- Debits must equal credits in every journal entry.
- Posted journal entries cannot be edited or deleted.

STATES:
- Journal Entry: Draft → Posted

=== SECTION: Net Assets & Contributions ===

CLASSIFICATIONS:
- Net Assets:
  - Without Donor Restrictions
  - With Donor Restrictions

RULES:
- Contributions must be classified as either with or without donor restrictions upon receipt.
- Board-designated funds must remain classified as Net Assets without donor restrictions.

WORKFLOWS:
- Receiving Unrestricted Funds: Increase asset (Cash) → Increase revenue in the "Without Donor Restrictions" class.
- Receiving Restricted Funds: Increase asset (Cash) → Increase revenue in the "With Donor Restrictions" class.
- Releasing Restricted Funds: When a restricted donation is spent for its intended purpose, an entry is made to move the amount from "With Donor Restrictions" to "Without Donor Restrictions".

=== SECTION: Expenses ===

CLASSIFICATIONS:
- Expenses must be classified by **Function**:
  - Program Services (can have multiple distinct programs)
  - Support Services
    - Management and General
    - Fundraising and Development
- Expenses are also classified by **Nature** (e.g., Salaries, Rent, Utilities via the Chart of Accounts).

RULES:
- The system must support allocating a single expense amount (e.g., one salary payment) across multiple functional classifications.

=== SECTION: Financial Reporting ===

CALCULATIONS:
- Total Assets = Liabilities + Net Assets
- Change in Net Assets = (Revenues + Gains) - (Expenses + Losses)

REPORTS:
- Statement of Financial Position: Assets, Liabilities, and Net Assets (broken down by restriction type) at a point in time.
- Statement of Activities: Revenues and expenses over a period, with separate columns showing the change in Net Assets `With` and `Without Donor Restrictions`. Must include a "Net assets released from restrictions" line.
- Statement of Functional Expenses: A matrix report with expenses by `Nature` (e.g., salaries, rent) as rows and by `Function` (e.g., Program A, Fundraising) as columns.
- Statement of Cash Flows: Changes in cash from Operating, Investing, and Financing activities.
- Budget vs. Actual: Compares budgeted amounts to actual results by program, function, and/or grant.

=== SECTION: Budgeting ===

ENTITIES:
- Budget: fiscal period, line items
- Budget Line Item: account, functional classification, amount

RULES:
- Budgeting must be possible by program, function, and nature of expense/revenue.





=== SECTION: Break-even & CVP Analysis ===

ENTITIES:
- **Analysis Scenario**: name, description, time period (e.g., weekly, monthly, annual)
- **Product/Service**: name, selling price per unit
- **Variable Expense**: name, cost per unit
- **Fixed Expense**: name, total cost for the period
- **Target Profit**: desired profit amount

RULES:
- All expenses must be classified as either fixed or variable for the calculation.
- Mixed expenses (part fixed, part variable) must be separated into their respective components.
- Selling price per unit and variable cost per unit are assumed to be constant.

CALCULATIONS:
- **Contribution Margin per Unit** = Selling Price per Unit - Total Variable Expenses per Unit
- **Contribution Margin Ratio** = Contribution Margin per Unit / Selling Price per Unit
- **Break-even Point in Units** = Total Fixed Expenses / Contribution Margin per Unit
- **Break-even Point in Sales Dollars** = Total Fixed Expenses / Contribution Margin Ratio
- **Units to Achieve Target Profit** = (Total Fixed Expenses + Target Profit) / Contribution Margin per Unit
- **Sales Dollars to Achieve Target Profit** = (Total Fixed Expenses + Target Profit) / Contribution Margin Ratio

WORKFLOWS:
- **Calculate Break-even Point**:
    1. Sum all Fixed Expenses for the period.
    2. Sum all Variable Expenses per unit.
    3. Calculate Contribution Margin per Unit.
    4. Calculate Break-even Point in Units and/or Sales Dollars.
- **Calculate for Target Profit**:
    1. Complete all steps for break-even calculation.
    2. Add Target Profit amount to Total Fixed Expenses.
    3. Recalculate required units and/or sales dollars.

CLASSIFICATIONS:
- **Expense Type**: Variable, Fixed, Mixed (Semi-Variable)

REPORTS:
- **Break-even Analysis Summary**: Shows inputs (Fixed Costs, Variable Costs, Price) and calculated outputs (Contribution Margin, BEP in Units, BEP in Dollars).
- **Target Profit Scenario**: Shows inputs (including Target Profit) and calculated outputs (Target Units, Target Sales Dollars).
- **Verification Schedule (Pro-forma Income Statement)**:
    - Sales (at break-even or target level)
    - Less: Variable Expenses
    - Equals: Contribution Margin
    - Less: Fixed Expenses
    - Equals: Net Profit (should be zero at break-even)

STATES:
- N/A

NOTES:
- The base model assumes a single product. The system may need to handle a multi-product analysis. [?]






=== SECTION: Cost Behavior ===

ENTITIES:
- **Expense:** amount, date, classification (Variable, Fixed, Mixed), associated location/department
- **Revenue:** amount, date, associated location/department

RULES:
- An expense must be classifiable by its behavior in relation to sales or other activity drivers.

CALCULATIONS:
- **Total Variable Expense** = Activity Volume * Per-Unit Variable Rate (or % of Sales)
- **Total Mixed Expense** = Fixed Component Amount + (Activity Volume * Per-Unit Variable Rate)

CLASSIFICATIONS:
- **Expense Behavior:**
    - Variable
    - Fixed
    - Mixed

---

=== SECTION: Decision Analysis & Forecasting ===

ENTITIES:
- **Analysis Scenario:** description, time period
- **Scenario Line Item:** type (Revenue, Expense), description, projected amount, behavior (Variable, Fixed)

RULES:
- Decision analysis models must exclude past (sunk) costs.
- Decision analysis models must exclude costs and revenues that do not change between alternatives.

CALCULATIONS:
- **Projected Net Income / (Loss) for a Scenario** = Sum of Projected Incremental Revenues - Sum of Projected Incremental Expenses
- **Contribution Margin** = Projected Revenues - Projected Variable Expenses

WORKFLOWS:
- **Evaluating a New Venture/Decision:**
    1. Identify all future revenues that will change due to the decision.
    2. Identify all future expenses that will change due to the decision.
    3. Calculate the projected impact on net income.

REPORTS:
- **Incremental Profit/Loss Analysis:** A report for a specific scenario showing only the additional (differential) revenues, expenses, and resulting net income.

---

=== SECTION: Performance Monitoring ===

ENTITIES:
- **Production Record:** date, employee_id, product_id, quantity_produced, labor_hours_spent, sales_value_of_production
- **Store Traffic Log:** date, location_id, number_of_entrants
- **Benchmark/Standard:** metric_name (e.g., Labor % of Sales), value

CALCULATIONS:
- **Labor Cost as % of Sales Value** = (Total Labor Cost / Total Sales Value) * 100
- **Production Rate (Productivity)** = Quantity Produced / Labor Hours Spent
- **Sales Conversion Rate** = (Number of Sales Transactions / Number of Store Entrants) * 100

REPORTS:
- **Labor Efficiency Report:** Compares actual labor cost as a percentage of sales against a defined benchmark.
- **Production Productivity Report:** Lists production rates by employee, product, and time period.
- **Store Conversion Rate Report:** Shows the sales conversion rate by location and time period.






=== SECTION: Cost Behavior ===

ENTITIES:
- **Expense:** amount, date, classification (Variable, Fixed, Mixed), associated location/department
- **Revenue:** amount, date, associated location/department

RULES:
- An expense must be classifiable by its behavior in relation to sales or other activity drivers.

CALCULATIONS:
- **Total Variable Expense** = Activity Volume * Per-Unit Variable Rate (or % of Sales)
- **Total Mixed Expense** = Fixed Component Amount + (Activity Volume * Per-Unit Variable Rate)

CLASSIFICATIONS:
- **Expense Behavior:**
    - Variable
    - Fixed
    - Mixed

---

=== SECTION: Decision Analysis & Forecasting ===

ENTITIES:
- **Analysis Scenario:** description, time period
- **Scenario Line Item:** type (Revenue, Expense), description, projected amount, behavior (Variable, Fixed)

RULES:
- Decision analysis models must exclude past (sunk) costs.
- Decision analysis models must exclude costs and revenues that do not change between alternatives.

CALCULATIONS:
- **Projected Net Income / (Loss) for a Scenario** = Sum of Projected Incremental Revenues - Sum of Projected Incremental Expenses
- **Contribution Margin** = Projected Revenues - Projected Variable Expenses

WORKFLOWS:
- **Evaluating a New Venture/Decision:**
    1. Identify all future revenues that will change due to the decision.
    2. Identify all future expenses that will change due to the decision.
    3. Calculate the projected impact on net income.

REPORTS:
- **Incremental Profit/Loss Analysis:** A report for a specific scenario showing only the additional (differential) revenues, expenses, and resulting net income.

---

=== SECTION: Performance Monitoring ===

ENTITIES:
- **Production Record:** date, employee_id, product_id, quantity_produced, labor_hours_spent, sales_value_of_production
- **Store Traffic Log:** date, location_id, number_of_entrants
- **Benchmark/Standard:** metric_name (e.g., Labor % of Sales), value

CALCULATIONS:
- **Labor Cost as % of Sales Value** = (Total Labor Cost / Total Sales Value) * 100
- **Production Rate (Productivity)** = Quantity Produced / Labor Hours Spent
- **Sales Conversion Rate** = (Number of Sales Transactions / Number of Store Entrants) * 100

REPORTS:
- **Labor Efficiency Report:** Compares actual labor cost as a percentage of sales against a defined benchmark.
- **Production Productivity Report:** Lists production rates by employee, product, and time period.
- **Store Conversion Rate Report:** Shows the sales conversion rate by location and time period.






=== SECTION: Capital Budgeting & Investment Analysis ===

ENTITIES:
- `Capital Project`: description, initial investment cost, salvage value, financial useful life, tax useful life, status
- `Project Cash Flow`: associated project, year, amount (inflow/outflow)
- `Company Settings`: default discount rate, income tax rate

RULES:
- Non-discretionary projects (e.g., safety, compliance) are prioritized over profitability-based projects.
- Net Present Value (NPV) and Internal Rate of Return (IRR) are the preferred evaluation models.
- A project is considered financially acceptable if its NPV is greater than zero.
- Projects can be ranked by their IRR; a higher IRR is more profitable.

CALCULATIONS:
- `Straight-Line Depreciation` = (Cost - Salvage Value) / Financial Useful life
- `Average Investment` = (Initial Investment + Salvage Value) / 2
- `Average Annual Net Income` = Average Annual Savings/Revenues - Average Annual Expenses (including depreciation)
- `Accounting Rate of Return (ARR)` = Average Annual Net Income / Investment Amount (can use initial or average investment, and before or after tax income)
- `Payback Period` = Time required for cumulative net cash flows to equal the initial investment
- `Net Present Value (NPV)` = Sum of the present values of all future cash flows - Initial Investment
- `Internal Rate of Return (IRR)` = The discount rate that results in a Net Present Value of zero
- `Maximum Acquisition Price` = The NPV of a target's future expected cash flows (including terminal value) at a required rate of return

WORKFLOWS:
- `Capital Budgeting`: List all proposals → Prioritize mandatory projects → Rank remaining projects by profitability (IRR) → Fund projects down the list until the budget is exhausted.
- `Project Evaluation`: Estimate project cash flows → Calculate key metrics (NPV, IRR, Payback) → Compare metrics to company standards → Approve or reject.

CLASSIFICATIONS:
- `Asset Types`: Long-term Assets (e.g., Equipment)
- `Expense Types`: Depreciation Expense, Income Tax Expense
- `Cash Flow Types`: Initial Investment (outflow), Operating Cash Flow (inflow), Terminal Value (inflow)

REPORTS:
- `Project Proposal Summary`: Displays key data and calculated metrics (NPV, IRR, Payback Period, ARR) for a single project.
- `Capital Budget Ranking`: A list of all proposed projects, sorted by IRR or NPV, showing their cost and profitability.

STATES:
- `Capital Project`: Proposed → Approved → Funded → Rejected

NOTES:
- Financial depreciation methods (e.g., straight-line) can differ from tax depreciation methods (e.g., accelerated), impacting tax-related cash flows.
- [?] Specific accelerated depreciation schedules (e.g., MACRS) for tax calculations need to be defined.





=== SECTION: Core Concepts ===

ENTITIES:
- Product: direct material cost, direct labor cost, allocated overhead cost
- Cost Account: description, type (Manufacturing Overhead, Nonmanufacturing)
- Department: name, type (Production, Service)

RULES:
- Manufacturing overhead must be included in product costs for inventory and Cost of Goods Sold (COGS).
- Nonmanufacturing costs (SG&A, Interest) are period expenses, not product costs.
- For internal analysis, nonmanufacturing costs can be assigned to products to assess true profitability.

CALCULATIONS:
- Total Product Cost = Direct Material + Direct Labor + Allocated Manufacturing Overhead

CLASSIFICATIONS:
- Cost Types:
    - Manufacturing: Direct Material, Direct Labor, Manufacturing Overhead
    - Nonmanufacturing: Selling, General & Administrative (SG&A), Interest Expense
- Inventory Accounts: Work-in-Process Inventory, Finished Goods Inventory

REPORTS:
- Balance Sheet: Shows value of Work-in-Process and Finished Goods inventory, which includes allocated overhead.
- Income Statement: Reports COGS (including allocated overhead) separately from SG&A and Interest Expense.

---

=== SECTION: Overhead Allocation ===

ENTITIES:
- Allocation Method: allocation base (e.g., Direct Labor Hours, Machine Hours)

RULES:
- The allocation base must have a direct correlation to the incurrence of overhead costs.

CALCULATIONS:
- Predetermined Overhead Rate = Total Budgeted Manufacturing Overhead / Total Budgeted Amount of Allocation Base
- Allocated Overhead per Product = Predetermined Overhead Rate * Quantity of Allocation Base used by Product
- Departmental Overhead Rate = Total Department Costs / Total Department Allocation Base

WORKFLOWS:
- Plant-Wide Rate Allocation:
    1. Calculate one overhead rate for the entire factory.
    2. Apply the single rate to all products based on their usage of the allocation base.
- Departmental Rate Allocation:
    1. Allocate costs from Service Departments to Production Departments. [?] (Method not specified in text)
    2. Calculate a separate overhead rate for each Production Department.
    3. As a product moves through departments, apply each department's rate based on the product's usage of that department's allocation base.
    4. Sum the allocated costs from all departments for the product's total overhead cost.







=== SECTION: Nonmanufacturing Overhead ===

ENTITIES:
- Cost: type (Manufacturing, Nonmanufacturing), description, amount
- Activity: description, associated cost pool
- Product: identifier
- Customer: identifier

RULES:
- Nonmanufacturing costs cannot be assigned to Inventory or Cost of Goods Sold for external financial reporting.
- Nonmanufacturing costs must be expensed in the period they are incurred.
- Allocation of nonmanufacturing costs to products or customers is for internal reporting only.
- Selling prices must cover all costs (manufacturing and nonmanufacturing) plus a profit margin.

CALCULATIONS:
- Internal Product/Customer Profitability = Selling Price - (Manufacturing Costs + Allocated Nonmanufacturing Costs)
- Gross Profit (GAAP) = Sales - Cost of Goods Sold

WORKFLOWS:
- Financial Reporting of Nonmanufacturing Costs: Incur cost → Expense on Income Statement
- Internal Allocation of Nonmanufacturing Costs (ABC):
    1. Identify activities causing nonmanufacturing costs
    2. Measure the cost of those activities
    3. Identify products/customers using the activities
    4. Assign activity costs to products/customers

CLASSIFICATIONS:
- Cost Type:
    - Manufacturing Cost (Product Cost)
        - Direct Material
        - Direct Labor
        - Manufacturing Overhead
    - Nonmanufacturing Cost (Period Cost)
        - Selling, General & Administrative (SG&A)
        - Interest Expense
- Examples of Nonmanufacturing Activities:
    - Servicing accounts
    - Invoicing customers
    - Processing payments
    - IT system maintenance
    - Financing assets
    - Prospecting new accounts

REPORTS:
- Income Statement (External): Reports Nonmanufacturing Costs as SG&A and Interest Expense.
- Balance Sheet (External): Reports Inventory value, which must exclude nonmanufacturing costs.
- Product/Customer Profitability Report (Internal): Shows sales, manufacturing costs, and allocated nonmanufacturing costs for a specific product or customer.

STATES:
- N/A

NOTES:
- The system must support two different cost treatments: one for GAAP-compliant external reporting and another for internal management decision-making.






=== SECTION: Activity Based Costing ===

**ENTITIES:**
- **Activity:** name, total overhead cost (cost pool)
- **Cost Driver:** name (e.g., number of setups, machine hours, weight), total annual quantity
- **Product:** identifier, properties linked to cost drivers (e.g., weight per unit, production rate per hour)
- **Production Batch:** product identifier, quantity of units, consumption of relevant cost drivers

**RULES:**
- The sum of all activity cost pools must equal the total manufacturing overhead being allocated.

**CALCULATIONS:**
- **Activity Rate** = Total Cost for an Activity / Total Quantity of its Cost Driver
- **Overhead Assigned to Batch** = Sum of (Activity Rate * Quantity of Driver consumed by the batch) for all activities
- **Overhead Cost Per Unit** = Overhead Assigned to Batch / Number of units in batch
- **Traditional Overhead Rate** = Total Manufacturing Overhead / Total Quantity of a single allocation base (e.g., total machine hours)

**WORKFLOWS:**
- **ABC Setup:**
    1. Identify activities.
    2. Assign total overhead costs to activity cost pools.
    3. Select a cost driver for each activity.
    4. Calculate the rate for each activity.
- **Product Costing:**
    1. Determine a batch's consumption of each cost driver.
    2. Apply activity rates to consumption quantities.
    3. Sum costs to get total overhead for the batch.
    4. Divide by units to get cost per unit.

**CLASSIFICATIONS:**
- **Cost Levels:** Batch-level costs (e.g., machine setups)

**REPORTS:**
- **Product Cost Comparison:** Shows overhead cost per unit for a product calculated via ABC vs. a Traditional method.
- **Product Overhead Breakdown:** Details the amount of overhead cost assigned to a product from each specific activity.

**STATES:**
- (None mentioned)

**NOTES:**
- ABC allocation is a two-stage process: 1) overhead to activities, 2) activities to products.
- The system must support comparison between ABC and traditional, single-driver costing methods.






=== SECTION: Standard Costing ===

ENTITIES:
- **Standard:** input_type (material, labor, VOH, FOH), standard_quantity_per_product_unit, standard_rate
- **Product:** name, identifier
- **Inventory_Direct_Material:** material_identifier, quantity_on_hand, standard_cost_per_unit
- **Inventory_Finished_Good:** product_identifier, quantity_on_hand, total_standard_cost
- **Inventory_Work_In_Process:** [Mentioned as a concept, but not used in examples]
- **Production_Record:** product_identifier, good_output_quantity, period
- **Material_Purchase:** material_identifier, actual_quantity_purchased, actual_total_cost
- **Material_Usage:** material_identifier, actual_quantity_used, associated_production_record
- **Labor_Usage:** actual_hours_worked, actual_rate_paid, associated_production_record
- **Overhead_Actual_Cost:** overhead_type (Variable, Fixed), actual_amount, period
- **Variance:** type, amount, status (Favorable/Unfavorable), period

RULES:
- All inventory is carried at standard cost.
- A debit balance in a variance account is unfavorable.
- A credit balance in a variance account is favorable.
- Direct Material Price Variance is calculated and recorded at the time of purchase/receipt.
- All other variances (Usage, Rate, Efficiency, etc.) are calculated based on the actual *good output* of a period.
- Unfavorable variances resulting from inefficiency must be expensed, not capitalized into inventory.
- Insignificant variance amounts can be closed entirely to Cost of Goods Sold (COGS).
- Significant variances from unrealistic standards must be allocated to inventory and COGS.

CALCULATIONS:
- **Standard Quantity Allowed (Materials):** Good Output Quantity * Standard Material Quantity per Unit
- **Standard Hours Allowed (Labor/OH):** Good Output Quantity * Standard Labor Hours per Unit
- **DM Price Variance:** (Actual Cost of Purchase) - (Actual Quantity Purchased * Standard Rate)
- **DM Usage Variance:** (Standard Quantity Allowed - Actual Quantity Used) * Standard Rate
- **DL Rate Variance:** (Actual Rate - Standard Rate) * Actual Hours Worked
- **DL Efficiency Variance:** (Standard Hours Allowed - Actual Hours Worked) * Standard Rate
- **Variable OH Spending Variance:** Actual Variable OH Cost - (Actual Hours Worked * Standard Variable OH Rate)
- **Variable OH Efficiency Variance:** (Standard Hours Allowed - Actual Hours Worked) * Standard Variable OH Rate
- **Standard Fixed OH Rate:** Total Budgeted Fixed OH Cost / Total Budgeted Activity Base (e.g., Standard Hours)
- **Fixed OH Budget Variance:** Actual Fixed OH Cost - Budgeted Fixed OH Cost
- **Applied Fixed OH:** Standard Hours Allowed * Standard Fixed OH Rate
- **Fixed OH Volume Variance:** Budgeted Fixed OH Cost - Applied Fixed OH

WORKFLOWS:
- **Material Purchasing:** Receive materials → Debit Direct Material Inventory (Actual Qty * Standard Rate) → Credit Accounts Payable (Actual Cost) → Record DM Price Variance.
- **Material Usage in Production:** Record good output → Debit WIP/FG (Standard Qty Allowed * Standard Rate) → Credit Direct Material Inventory (Actual Qty Used * Standard Rate) → Record DM Usage Variance.
- **Labor Usage in Production:** Record good output → Debit WIP/FG (Standard Hours Allowed * Standard Rate) → Credit Wages Payable (Actual Hours * Actual Rate) → Record DL Rate and Efficiency Variances.
- **Overhead Application:** Record good output → Debit WIP/FG (Standard Hours Allowed * Standard Rate) → Credit Overhead Applied → Record all OH variances.
- **Period-End Variance Disposition:** Assess variance significance → If insignificant, close to COGS → If significant (inefficiency), close to COGS → If significant (bad standard), allocate to inventories and COGS.

CLASSIFICATIONS:
- **Cost Components:** Direct Material, Direct Labor, Variable Manufacturing Overhead, Fixed Manufacturing Overhead
- **Inventory Types:** Direct Materials, Work-in-Process (WIP), Finished Goods (FG)
- **Variance Types:**
    - Direct Material: Price, Usage
    - Direct Labor: Rate, Efficiency
    - Variable Overhead: Spending, Efficiency
    - Fixed Overhead: Budget, Volume

REPORTS:
- **Variance Analysis:** For a period, shows standard costs, actual costs, and all calculated variances, grouped by cost component.
- **Income Statement:** COGS is stated at standard cost, adjusted by the net amount of variances closed to it.
- **Balance Sheet:** Inventory accounts are stated at standard cost, adjusted by any allocated variances.

STATES:
- **Variance:** Favorable, Unfavorable
- **Variance Account:** Open → Closed (to COGS or Allocated)







