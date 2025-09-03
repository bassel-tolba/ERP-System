


--- END OF FILE purchase_order_view_content.html ---
--- START OF FILE ledger_content.html ---

{% load static inventory_extras %}
<div class="d-flex justify-content-between align-items-center mb-4">
    <h1 class="mb-0 h2">كشف حساب المخزون</h1>
    <a id="printReportBtn" href="#" class="btn btn-outline-secondary {% if not request.GET %}disabled{% endif %}" target="_blank">
        <i class="bi bi-printer-fill me-2"></i>طباعة التقرير
    </a>
</div>
<div class="card shadow-sm mb-4">
    <div class="card-header">
        <h5 class="mb-0"><i class="bi bi-filter-circle-fill me-2"></i>خيارات البحث والتصفية</h5>
    </div>
    <div class="card-body">
        <form id="ledgerFilterForm" method="GET" action="{% url 'inventory:ledger' %}">
            <div class="row g-3 align-items-end">
                <div class="col-md-3">
                    <label for="product_id" class="form-label">المنتج</label>
                    <select name="product_id" id="product_id" class="form-select searchable-select">
                        <option value="">-- كل المنتجات --</option>
                        {% for product in all_primitive_products %}
                        <option value="{{ product.id }}" {% if request.GET.product_id == product.id|stringformat:"s" %}selected{% endif %}>{{ product.name }} ({{ product.code }})</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="col-md-3">
                    <label for="company_id" class="form-label">الشركة الموردة</label>
                    <select name="company_id" id="company_id" class="form-select searchable-select">
                        <option value="">-- كل الشركات --</option>
                        {% for company in all_companies %}
                        <option value="{{ company.id }}" {% if request.GET.company_id == company.id|stringformat:"s" %}selected{% endif %}>{{ company.name }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="col-md-3">
                    <label for="tags" class="form-label">وسوم السجلات</label>
                    <select name="tags" id="tags" class="form-select searchable-select" multiple>
                        {% for tag in all_tags %}
                        <option value="{{ tag.id }}" {% if tag.id|stringformat:"s" in request.GET.getlist('tags') %}selected{% endif %}>{{ tag.name }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="col-md-3">
                    <label for="qc_no" class="form-label">رقم QC</label>
                    <input type="text" name="qc_no" id="qc_no" class="form-control" value="{{ request.GET.qc_no|default:'' }}">
                </div>
                <div class="col-md-4">
                    <label for="start_date" class="form-label">من تاريخ</label>
                    <input type="text" name="start_date" id="start_date" class="form-control datepicker" value="{{ request.GET.start_date|default:'' }}">
                </div>
                <div class="col-md-4">
                    <label for="end_date" class="form-label">إلى تاريخ</label>
                    <input type="text" name="end_date" id="end_date" class="form-control datepicker" value="{{ request.GET.end_date|default:'' }}">
                </div>
                <div class="col-md-4 d-flex align-items-end">
                    <button type="submit" class="btn btn-primary w-50 me-2"><i class="bi bi-search me-2"></i>بحث</button>
                    <a href="{% url 'inventory:ledger' %}" class="btn btn-secondary w-50"><i class="bi bi-eraser-fill me-2"></i>مسح</a>
                </div>
            </div>
        </form>
    </div>
</div>

{% if request.GET %}
    {% if transactions %}
    <div class="card shadow-sm">
        <div class="card-header">
             <h5 class="mb-0">نتائج البحث</h5>
             {% if request.GET.product_id %}
             <div class="d-flex justify-content-between align-items-center small text-muted mt-2">
                <span>الرصيد الافتتاحي (كمية): <strong>{{ opening_balance_for_period|floatformat:3 }}</strong> {{ unit }}</span>
                <span>الرصيد الافتتاحي (قيمة): <strong>{{ opening_value_for_period|floatformat:3 }}</strong></span>
             </div>
             {% endif %}
        </div>
        <div class="table-responsive">
            <table class="table table-hover table-striped mb-0">
                <thead class="table-light">
                    <tr>
                        <th rowspan="2">التاريخ</th>
                        <th rowspan="2">المنتج</th>
                        <th rowspan="2">البيان</th>
                        <th colspan="3" class="text-center border-start border-end">الكمية</th>
                        <th colspan="3" class="text-center">القيمة</th>
                        <th rowspan="2"></th>
                    </tr>
                    <tr class="table-light">
                        <th class="text-center">التغيير</th>
                        <th class="text-center border-start">قبل</th>
                        <th class="text-center border-end">بعد</th>
                        <th class="text-center">التغيير</th>
                        <th class="text-center border-start">قبل</th>
                        <th class="text-center">بعد</th>
                    </tr>
                </thead>
                <tbody>
                    {% for t in transactions %}
                    <tr>
                        <td>{{ t.date|date:"Y-m-d H:i" }}</td>
                        <td>{{ t.product_name }}</td>
                        <td>
                            {{ t.description }}
                            {% if t.type == 'OUT' and t.batch_id %}
                                <a href="{% url 'inventory:view_batch' t.batch_id %}" target="_blank"><i class="bi bi-box-arrow-up-right small"></i></a>
                            {% endif %}
                        </td>
                        <td class="text-center fw-bold {% if t.quantity_change > 0 %}text-success{% else %}text-danger{% endif %}">{{ t.quantity_change|floatformat:3 }}</td>
                        <td class="text-center text-muted border-start">{{ t.balance_before|floatformat:3|default:"---" }}</td>
                        <td class="text-center fw-bold border-end">{{ t.balance_after|floatformat:3|default:"---" }}</td>
                        <td class="text-center fw-bold {% if t.value_change > 0 %}text-success{% elif t.value_change < 0 %}text-danger{% endif %}">{{ t.value_change|floatformat:3|default:"---" }}</td>
                        <td class="text-center text-muted border-start">{{ t.value_before|floatformat:3|default:"---" }}</td>
                        <td class="text-center fw-bold">{{ t.value_after|floatformat:3|default:"---" }}</td>
                        <td class="text-end">
                             <button class="btn btn-sm btn-outline-primary" data-bs-toggle="modal" data-bs-target="#detailsModal"
                                data-type="{{ t.type }}" data-date="{{ t.date|date:'Y-m-d H:i' }}"
                                data-product-name="{{ t.product_name }}" data-product-code="{{ t.product_code }}"
                                data-actual-qty="{{ t.quantity_change|my_abs|floatformat:'-3' }}" data-company-name="{{ t.company_name|default:'N/A' }}"
                                data-qc-no="{{ t.qc_no|default:'N/A' }}" data-shop-order-no="{{ t.shop_order_number|default:'N/A' }}"
                                data-batch-no="{{ t.batch_number|default:'N/A' }}" data-final-product="{{ t.final_product_name|default:'N/A' }}"
                                data-theoretical-qty="{{ t.theoretical_quantity|floatformat:3|default:'N/A' }}"
                                data-batch-id="{{ t.batch_id|default:'' }}">
                                <i class="bi bi-info-circle"></i>
                            </button>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
    {% else %}
    <div class="alert alert-info"><i class="bi bi-search me-2"></i> لا توجد حركات مطابقة لمعايير البحث المحددة.</div>
    {% endif %}
{% else %}
 <div class="alert alert-secondary"><i class="bi bi-info-circle-fill me-2"></i> الرجاء استخدام الفلاتر أعلاه لعرض كشف حساب.</div>
{% endif %}

{% include "inventory/partials/ledger_modals.html" %}
--- END OF FILE ledger_content.html ---
--- START OF FILE print_ledger.html ---

{% load static inventory_extras %}
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ report_title }}</title>
    <link rel="stylesheet" href="{% static 'css/bootstrap.css' %}">
    <link rel="stylesheet" href="{% static 'css/google-fonts.css' %}">
    <style>
        :root {
            --gipco-primary: #0d6efd;
            --gipco-secondary: #6c757d;
            --gipco-light-gray: #f8f9fa;
        }
        body {
            font-family: 'Cairo', sans-serif;
            background-color: #FFF;
            color: #212529;
        }
        .page {
            width: 21cm;
            min-height: 29.7cm;
            padding: 1.5cm;
            margin: 1cm auto;
            border: 1px #D3D3D3 solid;
            border-radius: 5px;
            background: white;
            box-shadow: 0 0 5px rgba(0, 0, 0, 0.1);
            position: relative;
        }
        .page-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 2px solid var(--gipco-primary);
            padding-bottom: 1rem;
            margin-bottom: 1.5rem;
        }
        .page-header .logo {
            font-size: 2.5rem;
            font-weight: 700;
            color: var(--gipco-primary);
        }
        .page-header .company-info h1 { margin: 0; font-size: 1.2rem; font-weight: 600; }
        .page-header .company-info p { margin: 0; font-size: 0.9rem; color: var(--gipco-secondary); }
        .report-title { text-align: center; margin-bottom: 1.5rem; }
        .report-title h2 { font-weight: 700; color: var(--gipco-primary); }
        .report-meta {
            font-size: 0.9rem;
            margin-bottom: 1.5rem;
            border: 1px solid #dee2e6;
            padding: 1rem;
            border-radius: .25rem;
            background-color: var(--gipco-light-gray);
        }
        .table { font-size: 0.8rem; }
        .table th, .table td { padding: 0.3rem; vertical-align: middle; }
        .table th { background-color: var(--gipco-light-gray); font-weight: 600; text-align: center; }
        .page-footer {
            position: absolute;
            bottom: 1.5cm;
            left: 1.5cm;
            right: 1.5cm;
            text-align: center;
            font-size: 0.75rem;
            color: var(--gipco-secondary);
            border-top: 1px solid #dee2e6;
            padding-top: 0.5rem;
        }
        @media print {
            body, .page { margin: 0; box-shadow: none; border: none; border-radius: 0; }
        }
        @page { size: A4; margin: 0; }
    </style>
</head>
<body>
    <div class="page" id="summary-page">
        <div class="page-header">
            <div class="logo">GIPCCO</div>
            <div class="company-info text-end">
                <h1>شركة جيبكو للصناعات الكيماوية</h1>
                <p>قسم المخازن</p>
            </div>
        </div>
        <div class="report-title">
            <h2>{{ report_title }}</h2>
            <p class="text-muted">
                تقرير حركة المخزون للفترة من {{ start_date|default:"البداية" }} إلى {{ end_date|default:"النهاية" }}
            </p>
        </div>
        
        <div class="report-meta">
             {% if product_details %}
            <div class="row">
                <div class="col-6"><strong>الرصيد الافتتاحي (كمية):</strong></div>
                <div class="col-6 text-end"><strong>{{ opening_balance|floatformat:3 }} {{ product_details.unit }}</strong></div>
            </div>
            <div class="row">
                <div class="col-6"><strong>الرصيد الافتتاحي (قيمة):</strong></div>
                <div class="col-6 text-end"><strong>{{ opening_value|floatformat:3 }}</strong></div>
            </div>
            <hr class="my-2">
            <div class="row">
                <div class="col-6"><strong>الرصيد الختامي (كمية):</strong></div>
                <div class="col-6 text-end"><strong>{{ closing_balance|floatformat:3 }} {{ product_details.unit }}</strong></div>
            </div>
            <div class="row">
                <div class="col-6"><strong>الرصيد الختامي (قيمة):</strong></div>
                <div class="col-6 text-end"><strong>{{ closing_value|floatformat:3 }}</strong></div>
            </div>
            {% else %}
            <p class="mb-0 text-center">تقرير عام لكل المنتجات</p>
            {% endif %}
        </div>
        
        <div class="table-responsive">
            <table class="table table-sm table-bordered">
                <thead>
                    <tr>
                        <th rowspan="2">التاريخ</th>
                        <th rowspan="2">البيان</th>
                        <th colspan="2" class="text-center">التغيير</th>
                        <th colspan="2" class="text-center">الرصيد بعد</th>
                    </tr>
                    <tr>
                        <th>الكمية</th>
                        <th>القيمة</th>
                        <th>الكمية</th>
                        <th>القيمة</th>
                    </tr>
                </thead>
                <tbody>
                    {% for t in transactions %}
                    <tr>
                        <td>{{ t.date|date:"y-m-d" }}</td>
                        <td>{{ t.description }}</td>
                        <td class="text-center {% if t.quantity_change > 0 %}text-success{% else %}text-danger{% endif %}">
                            {{ t.quantity_change|floatformat:3|default:"-" }}
                        </td>
                        <td class="text-center {% if t.value_change > 0 %}text-success{% elif t.value_change < 0 %}text-danger{% endif %}">
                            {{ t.value_change|floatformat:3|default:"-" }}
                        </td>
                        <td class="text-center fw-bold">{{ t.balance_after|floatformat:3|default:"-" }}</td>
                        <td class="text-center fw-bold">{{ t.value_after|floatformat:3|default:"-" }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        <div class="page-footer">
            <div>
                <span>تاريخ الطباعة: {{ print_date|date:"Y-m-d H:i:s" }}</span>
            </div>
        </div>
    </div>
    <script>
        window.onload = function() { window.print(); };
    </script>
</body>
</html>
--- END OF FILE print_ledger.html ---