# gipcco_project/inventory/management/commands/seed_accounts.py

import json
from django.core.management.base import BaseCommand
from django.db import connection, transaction
from inventory.models import Account

# This data is transcribed directly from your provided Chart of Accounts.
# It is structured to be processed sequentially.
ACCOUNTS_DATA = [
    # Level 1
    {'code': '1', 'name': 'الاصول', 'parent_code': None},
    {'code': '2', 'name': 'الالتزامات', 'parent_code': None},
    {'code': '3', 'name': 'المصروفات', 'parent_code': None},
    {'code': '4', 'name': 'الايرادات', 'parent_code': None},
    {'code': '5', 'name': 'حقوق الملكية', 'parent_code': None},

    # Level 2 (Assets)
    {'code': '101', 'name': 'الأصول طويلة الأجل', 'parent_code': '1'},
    {'code': '102', 'name': 'الاصول المتداولة', 'parent_code': '1'},
    
    # Level 3 (Long-term Assets)
    {'code': '10101', 'name': 'الاصول الثابتة', 'parent_code': '101'},
    {'code': '10102', 'name': 'مشروعات تحت التنفيذ', 'parent_code': '101'},
    {'code': '10103', 'name': 'اصول غير ملموسة', 'parent_code': '101'},
    
    # Level 4 (Fixed Assets)
    {'code': '1010101', 'name': 'الأراضى', 'parent_code': '10101'},
    {'code': '1010102', 'name': 'مباني وانشاءات', 'parent_code': '10101'},
    {'code': '1010103', 'name': 'الات ومعدات', 'parent_code': '10101'},
    {'code': '1010104', 'name': 'وسائل نقل وانتقال', 'parent_code': '10101'},
    {'code': '1010105', 'name': 'اجهزة كمبيوتر واتصالات', 'parent_code': '10101'},
    {'code': '1010106', 'name': 'اثاث وتجهيزات', 'parent_code': '10101'},
    {'code': '1010107', 'name': 'عدد وادوات', 'parent_code': '10101'},
    {'code': '1010108', 'name': 'أجهزة معامل', 'parent_code': '10101'},
    {'code': '1010109', 'name': 'أجهزة كهربائبة', 'parent_code': '10101'},

    # Level 4 (Projects Under Construction)
    {'code': '1010202', 'name': 'مشروعات تحت التنفيذ - اصول غير ملموسة', 'parent_code': '10102'},
    {'code': '1010203', 'name': 'مشروعات تحت التنفيذ - اصول ملموسة', 'parent_code': '10102'},
    
    # Level 4 (Intangible Assets)
    {'code': '1010301', 'name': 'مواقع وإيميلات', 'parent_code': '10103'},

    # Level 3 (Current Assets)
    {'code': '10201', 'name': 'النقدية وما في حكمها', 'parent_code': '102'},
    {'code': '10202', 'name': 'المخزون', 'parent_code': '102'},
    {'code': '10203', 'name': 'حسابات العملاء (ذمم مدينة)', 'parent_code': '102'},
    {'code': '10204', 'name': 'مصروفات مدفوعة مقدما وارصدة مدينة أخرى', 'parent_code': '102'},

    # Level 4 (Cash)
    {'code': '1020101', 'name': 'صندوق المصنع', 'parent_code': '10201'},
    {'code': '1020102', 'name': 'أوراق القبض بالصندوق', 'parent_code': '10201'},
    {'code': '1020103', 'name': 'حسابات البنوك', 'parent_code': '10201'},

    # Level 4 (Inventory)
    {'code': '1020201', 'name': 'مخزون مواد خام', 'parent_code': '10202'},
    {'code': '1020202', 'name': 'مخزون قطع الغيار', 'parent_code': '10202'},
    {'code': '1020203', 'name': 'مخزون مواد تعبئة وتغليف', 'parent_code': '10202'},
    {'code': '1020204', 'name': 'مخزون منتج تام', 'parent_code': '10202'},
    {'code': '1020205', 'name': 'مخزون انتاج تحت التشغيل', 'parent_code': '10202'},
    {'code': '1020206', 'name': 'مخزون تحت الفحص', 'parent_code': '10202'},
    {'code': '1020207', 'name': 'مخزون الخدمات والمستهلكات', 'parent_code': '10202'},
    {'code': '1020208', 'name': 'مخزون مخلفات', 'parent_code': '10202'},
    
    # Level 4 (Customers)
    {'code': '1020301', 'name': 'حسابات عملاء - محاليل وأدوية', 'parent_code': '10203'},
    {'code': '1020302', 'name': 'حسابات عملاء - مستحضرات تجميل', 'parent_code': '10203'},

    # Level 4 (Prepaid Exp & Other Receivables)
    {'code': '1020401', 'name': 'عهد وسلف عاملين', 'parent_code': '10204'},
    {'code': '1020402', 'name': 'موردين دفعات مقدمة', 'parent_code': '10204'},
    {'code': '1020403', 'name': 'تامينات لدى الغير', 'parent_code': '10204'},
    {'code': '1020404', 'name': 'ضريبة القيمة المضافة (المدخلات)', 'parent_code': '10204'},
    {'code': '1020405', 'name': 'ارصدة مدينة اخرى', 'parent_code': '10204'},
    {'code': '1020406', 'name': 'ضريبة الخصم من المنبع (المسددة)', 'parent_code': '10204'},

    # Level 2 (Liabilities)
    {'code': '201', 'name': 'الالتزامات طويلة الأجل', 'parent_code': '2'},
    {'code': '202', 'name': 'الالتزامات المتداولة', 'parent_code': '2'},
    
    # Level 3 (Long-term Liabilities)
    {'code': '20101', 'name': 'دائنو شراء اصول ثابتة', 'parent_code': '201'},
    {'code': '20102', 'name': 'قروض طويلة الاجل', 'parent_code': '201'},
    
    # Level 3 (Current Liabilities)
    {'code': '20201', 'name': 'حسابات الموردين (ذمم دائنة)', 'parent_code': '202'},
    {'code': '20202', 'name': 'اوراق دفع', 'parent_code': '202'},
    {'code': '20203', 'name': 'المستحق الى اطراف ذات علاقة', 'parent_code': '202'},
    {'code': '20204', 'name': 'مصروفات مستحقة وارصدة دائنة اخرى', 'parent_code': '202'},
    {'code': '20205', 'name': 'مجمع الاهلاك', 'parent_code': '202'},
    
    # Level 4 (Related Parties)
    {'code': '2020302', 'name': 'جاري الشركاء', 'parent_code': '20203'},

    # Level 4 (Accrued Exp & Other Payables)
    {'code': '2020401', 'name': 'مصروفات مستحقة', 'parent_code': '20204'},
    {'code': '2020402', 'name': 'ضمانات الاعمال', 'parent_code': '20204'},
    {'code': '2020403', 'name': 'ارصدة دائنة اخرى', 'parent_code': '20204'},

    # Level 4 (Accumulated Depreciation) - Note: codes are long, handled as strings
    {'code': '20205010001', 'name': 'مجمع اهلاك مبانى وانشاءات', 'parent_code': '20205'},
    {'code': '20205010002', 'name': 'مجمع اهلاك الات ومعدات', 'parent_code': '20205'},
    {'code': '20205010003', 'name': 'مجمع اهلاك وسائل نقل وانتقال', 'parent_code': '20205'},
    {'code': '20205010004', 'name': 'مجمع اهلاك اجهزة كمبيوتر واتصالات', 'parent_code': '20205'},
    {'code': '20205010005', 'name': 'مجمع اهلاك اثاث وتجهيزات', 'parent_code': '20205'},
    {'code': '20205010006', 'name': 'مجمع اهلاك عدد وادوات', 'parent_code': '20205'},
    {'code': '20205010007', 'name': 'مجمع اهلاك اجهزة معمل', 'parent_code': '20205'},
    {'code': '20205010008', 'name': 'مجمع اهلاك اجهزة كهربائية', 'parent_code': '20205'},
    
    # Level 2 (Expenses)
    {'code': '301', 'name': 'المصروفات التشغيلية', 'parent_code': '3'},
    {'code': '302', 'name': 'مصروفات بيعية وعمومية وإدارية', 'parent_code': '3'},
    {'code': '303', 'name': 'مصروفات تمويلية', 'parent_code': '3'},
    {'code': '304', 'name': 'تكلفة البضاعة المباعة', 'parent_code': '3'},
    
    # Level 3 (COGS)
    {'code': '30401', 'name': 'تكلفة بضاعة مباعة - محاليل وأدوية', 'parent_code': '304'},
    {'code': '30402', 'name': 'تكلفة بضاعة مباعة - مستحضرات تجميل', 'parent_code': '304'},

    # Level 3 (Operating Expenses)
    {'code': '30101010001', 'name': 'أجور مباشرة (تشغيل)', 'parent_code': '301'},
    {'code': '30101010002', 'name': 'تأمينات اجتماعية (تشغيل)', 'parent_code': '301'},
    {'code': '30101010005', 'name': 'صيانة ومعدات (تشغيل)', 'parent_code': '301'},
    {'code': '30101010007', 'name': 'وقود ومحروقات (تشغيل)', 'parent_code': '301'},
    {'code': '30101010011', 'name': 'كهرباء (تشغيل)', 'parent_code': '301'},
    {'code': '30101010012', 'name': 'مياه (تشغيل)', 'parent_code': '301'},
    {'code': '30101010023', 'name': 'مستهلكات إنتاج ومعامل', 'parent_code': '301'},
    {'code': '30101010032', 'name': 'مصاريف اهلاك (تشغيل)', 'parent_code': '301'},
    {'code': '30101010033', 'name': 'مصروفات تشغيلية أخرى', 'parent_code': '301'},

    # Level 3 (SG&A Expenses)
    {'code': '30201010001', 'name': 'أجور ورواتب (إداري)', 'parent_code': '302'},
    {'code': '30201010050', 'name': 'تأمينات اجتماعية (إداري)', 'parent_code': '302'},
    {'code': '30201010022', 'name': 'إيجارات', 'parent_code': '302'},
    {'code': '30201010025', 'name': 'كهرباء ومياه واتصالات (إداري)', 'parent_code': '302'},
    {'code': '30201010037', 'name': 'صيانة عامة (إداري)', 'parent_code': '302'},
    {'code': '30201010043', 'name': 'مصروفات تسويقية ودعاية وإعلان', 'parent_code': '302'},
    {'code': '30201010024', 'name': 'أتعاب مهنية واستشارية', 'parent_code': '302'},
    {'code': '30201010021', 'name': 'رسوم حكومية واشتراكات', 'parent_code': '302'},
    {'code': '30201010008', 'name': 'مصاريف بنكية وعمولات', 'parent_code': '302'},
    {'code': '30201010039', 'name': 'أدوات مكتبية ومطبوعات', 'parent_code': '302'},
    {'code': '30201010026', 'name': 'مصروف اهلاك (إداري)', 'parent_code': '302'},
    {'code': '30201010047', 'name': 'فروق عملة', 'parent_code': '302'},
    {'code': '30201010018', 'name': 'مصروفات بيعية وعمومية أخرى', 'parent_code': '302'},

    # Level 3 (Financing Expenses)
    {'code': '30301010001', 'name': 'فوائد القروض', 'parent_code': '303'},

    # Level 2 (Revenue)
    {'code': '401', 'name': 'ايرادات النشاط', 'parent_code': '4'},
    {'code': '402', 'name': 'ايرادات أخرى', 'parent_code': '4'},

    # Level 3 (Operating Revenue)
    {'code': '4010101', 'name': 'مبيعات محاليل وادوية', 'parent_code': '401'},
    {'code': '4010102', 'name': 'مبيعات مستحضرات تجميل', 'parent_code': '401'},

    # Level 3 (Other Revenue)
    {'code': '4020101', 'name': 'ايراد بيع مخلفات (سكراب)', 'parent_code': '402'},
    {'code': '4020104', 'name': 'إيرادات أرباح بنكية', 'parent_code': '402'},
    {'code': '4020105', 'name': 'إيرادات أخرى متنوعة', 'parent_code': '402'},

    # Level 2 (Equity)
    {'code': '501', 'name': 'ارباح / خسارة العام', 'parent_code': '5'},
    {'code': '502', 'name': 'راس المال', 'parent_code': '5'},
    {'code': '503', 'name': 'أرباح وخسائر مرحلة', 'parent_code': '5'},

    # Level 3 (Capital)
    {'code': '5020101', 'name': 'رأس مال الشركاء', 'parent_code': '502'},
]


class Command(BaseCommand):
    help = 'Force deletes all existing accounts and seeds the Chart of Accounts from a predefined structure.'

    def _get_account_type(self, code):
        """Determines the account type based on the first digit of the code."""
        if code.startswith('1'):
            return Account.AccountType.ASSET
        if code.startswith('2'):
            return Account.AccountType.LIABILITY
        if code.startswith('3'):
            return Account.AccountType.EXPENSE
        if code.startswith('4'):
            return Account.AccountType.REVENUE
        if code.startswith('5'):
            return Account.AccountType.EQUITY
        return None # Should not happen with valid data

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('This command will completely WIPE the Chart of Accounts table.'))
        confirm = input('Are you sure you want to continue? (yes/no): ')

        if confirm.lower() != 'yes':
            self.stdout.write(self.style.ERROR('Operation cancelled.'))
            return

        self.stdout.write("Proceeding with account deletion and seeding...")

        # Step 1: Forcefully wipe the table using raw SQL to bypass constraints
        self.stdout.write(self.style.WARNING('Wiping existing accounts...'))
        with connection.cursor() as cursor:
            # TRUNCATE is faster and resets sequences in PostgreSQL
            # For SQLite, DELETE is the way.
            db_vendor = connection.vendor
            if db_vendor == 'postgresql':
                cursor.execute("TRUNCATE TABLE chart_of_accounts RESTART IDENTITY CASCADE;")
            else: # SQLite and MySQL
                cursor.execute("DELETE FROM chart_of_accounts;")
                if db_vendor == 'sqlite':
                    cursor.execute("DELETE FROM sqlite_sequence WHERE name='chart_of_accounts';")
        self.stdout.write(self.style.SUCCESS('Existing accounts wiped successfully.'))

        # Step 2: Seed the new accounts, handling parent relationships
        self.stdout.write("Seeding new accounts...")
        
        # A map to hold created account instances for quick parent lookup
        account_map = {}

        for acc_data in ACCOUNTS_DATA:
            code = acc_data['code']
            name = acc_data['name']
            parent_code = acc_data['parent_code']
            
            parent = None
            if parent_code:
                # Find the parent instance from the ones we've already created
                parent = account_map.get(parent_code)
                if not parent:
                    self.stdout.write(self.style.ERROR(f'Could not find parent with code {parent_code} for account {code}. Aborting.'))
                    raise Exception(f'Parent account {parent_code} not found.')

            account_type = self._get_account_type(code)
            
            account = Account.objects.create(
                code=code,
                name=name,
                account_type=account_type,
                parent=parent
            )
            
            # Store the created account instance in our map
            account_map[code] = account
            self.stdout.write(f"  Created account: {account.code} - {account.name}")

        self.stdout.write(self.style.SUCCESS('Chart of Accounts seeded successfully!'))