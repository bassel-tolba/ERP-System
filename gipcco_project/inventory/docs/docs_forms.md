# `forms.py` Manifest

This file defines the Django forms used for creating and validating manual `JournalEntry` objects. Django forms are a powerful way to handle data input and validation, separating the logic of the form from its presentation in the template.

## Key Components:

### 1. **`JournalEntryForm`**
   - **Purpose**: This is a `ModelForm` for the `JournalEntry` model. It handles the "header" part of the journal entry.
   - **Fields**: It includes fields for the `date`, `description`, and `notes` of the journal entry.
   - **Widgets**: It defines the HTML widgets to be used for rendering each field, assigning CSS classes for styling and JavaScript enhancements (e.g., using a `datetime-local` input for the date).

### 2. **`JournalEntryLineForm`**
   - **Purpose**: This is a `ModelForm` for the `JournalEntryLine` model, representing a single line within the journal entry.
   - **Fields**: It includes fields for the `account`, `entry_type` (Debit/Credit), and `amount`.
   - **Widgets**: It assigns CSS classes to the form elements to enable styling and JavaScript functionality, such as using the `select2` library for a searchable dropdown for the `account` field.
   - **Custom `__init__`**: The form is customized to ensure that the `account` dropdown only shows **leaf accounts** (i.e., accounts that do not have any child accounts). This is a critical validation rule, as financial transactions should only be posted to the most detailed level of the Chart of Accounts, not to parent/summary accounts.

### 3. **`BaseJournalEntryLineFormSet`**
   - **Purpose**: This is a custom **formset** class that provides validation for the entire set of `JournalEntryLine` forms as a whole. A formset is a Django abstraction that manages multiple instances of the same form on a single page.
   - **`clean()` Method**: This method contains the most important validation logic for a journal entry:
     - It calculates the sum of all `DEBIT` amounts and the sum of all `CREDIT` amounts across all the valid lines in the formset.
     - It raises a `ValidationError` if the `total_debit` does not equal the `total_credit`. This enforces the fundamental accounting principle of double-entry bookkeeping.
     - It also ensures that a journal entry has at least two lines.

### 4. **`JournalEntryLineFormSet`**
   - **Purpose**: This is the final, usable `inlineformset_factory` that brings all the pieces together.
   - **Configuration**:
     - It links the `JournalEntry` (parent model) with the `JournalEntryLine` (child model).
     - It specifies that it should use our custom `JournalEntryLineForm` for each line.
     - Crucially, it specifies that it should use our custom `BaseJournalEntryLineFormSet` for the overall validation, which enables the debit/credit balance check.
     - `extra=2`: Tells the formset to always display two empty forms for new lines.
     - `can_delete=True`: Allows users to delete existing lines.
     - `min_num=2`: Enforces that at least two lines must be submitted.

These components work together to provide a robust and user-friendly interface for manual journal entry creation, with strong server-side validation to ensure that only balanced and valid entries can be submitted.
