// gipcco_project/static/admin/js/inventory_consumption.js
// jQuery version - often more reliable in the Django admin

// This ensures we're using Django's bundled jQuery to avoid conflicts.
(function($) {
    $(document).ready(function() {
        
        const consumptionTypeSelect = $('#id_consumption_type');
        const fixedAssetRow = $('.field-fixed_asset');

        function toggleFixedAssetField() {
            if (consumptionTypeSelect.val() === 'capitalize') {
                fixedAssetRow.show(); // jQuery's way of showing an element
            } else {
                fixedAssetRow.hide(); // jQuery's way of hiding an element
            }
        }

        // --- Event Listeners ---
        
        // 1. Initial check when the page loads.
        toggleFixedAssetField();

        // 2. Add an event listener to the dropdown for changes.
        consumptionTypeSelect.on('change', toggleFixedAssetField);
    });
})(django.jQuery);