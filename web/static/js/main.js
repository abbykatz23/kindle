document.addEventListener("DOMContentLoaded", () => {
    const distanceInputs = document.querySelectorAll("input[name$='_distance']");
    const totalEl = document.querySelector("[data-week-total]");

    function updateWeekTotal() {
        if (!totalEl) return;
        let total = 0;
        distanceInputs.forEach((input) => {
            const val = parseFloat(input.value);
            if (!Number.isNaN(val)) total += val;
        });
        // Trim trailing zeros: 10.0 → 10, 5.50 → 5.5
        totalEl.textContent = Number.isInteger(total) ? total : parseFloat(total.toFixed(2));
    }

    // Auto-zero distance when a day is set to Rest, then recompute total
    document.querySelectorAll("select[name$='_type']").forEach((select) => {
        select.addEventListener("change", () => {
            const day = select.name.replace("_type", "");
            const distInput = document.querySelector(`input[name="${day}_distance"]`);
            if (distInput && select.value === "rest") {
                distInput.value = "0";
            }
            updateWeekTotal();
        });
    });

    distanceInputs.forEach((input) => {
        input.addEventListener("input", updateWeekTotal);
    });

    updateWeekTotal();
});
