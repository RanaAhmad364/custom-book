export function pricingRecordDefaults(kind, currency = "PKR") {
  const defaults = {
    tier: { code: "", name: "", description: "", basePrice: "0.00", currency, active: true },
    pagePricing: { tierId: "", minimumPages: 24, maximumPages: 80, pricePerPage: "0.00" },
    shipping: {
      countryCode: "",
      regionCode: "",
      serviceCode: "",
      serviceName: "",
      price: "0.00",
      currency,
      estimatedDaysMin: "",
      estimatedDaysMax: "",
      active: true,
    },
    size: { code: "", name: "", widthMm: "", heightMm: "", active: true },
    cover: { name: "", description: "", active: true },
    paper: { name: "", description: "", weightGsm: "", active: true },
    variant: {
      sku: "",
      productId: "",
      sizeId: "",
      coverTypeId: "",
      paperTypeId: "",
      basePrice: "0.00",
      currency,
      active: true,
    },
  };
  if (!defaults[kind]) throw new Error("This pricing record type cannot be created.");
  return { ...defaults[kind], kind, __create: true };
}

function validAmount(value) {
  return /^(?:0|[1-9]\d*)(?:\.\d{1,2})?$/.test(String(value ?? "").trim());
}

function positiveInteger(value, optional = false) {
  if (optional && (value === "" || value === null || value === undefined)) return true;
  return Number.isInteger(Number(value)) && Number(value) > 0;
}

export function validatePricingRecord(kind, record) {
  const errors = {};
  const requireText = (field, label) => {
    if (typeof record[field] !== "string" || !record[field].trim()) errors[field] = `Enter ${label}.`;
  };
  const currency = () => {
    if (!/^[A-Za-z]{3}$/.test(String(record.currency ?? "").trim())) {
      errors.currency = "Use a three-letter currency code.";
    }
  };
  const amount = (field, label) => {
    if (!validAmount(record[field])) errors[field] = `Enter a non-negative ${label} with up to two decimal places.`;
  };

  if (kind === "tier") {
    requireText("code", "a tier code");
    requireText("name", "a tier name");
    amount("basePrice", "base price");
    currency();
  } else if (kind === "pagePricing") {
    if (!record.tierId) errors.tierId = "Choose a pricing tier.";
    if (!positiveInteger(record.minimumPages)) errors.minimumPages = "Enter a positive minimum page count.";
    if (!positiveInteger(record.maximumPages)) errors.maximumPages = "Enter a positive maximum page count.";
    if (positiveInteger(record.minimumPages) && positiveInteger(record.maximumPages)
      && Number(record.maximumPages) < Number(record.minimumPages)) {
      errors.maximumPages = "Maximum pages must be at least the minimum.";
    }
    amount("pricePerPage", "per-page price");
  } else if (kind === "shipping") {
    requireText("countryCode", "a country code");
    requireText("serviceCode", "a service code");
    requireText("serviceName", "a service name");
    if (!/^[A-Za-z]{2}$/.test(String(record.countryCode ?? "").trim())) errors.countryCode = "Use a two-letter country code.";
    amount("price", "shipping price");
    currency();
    for (const field of ["estimatedDaysMin", "estimatedDaysMax"]) {
      if (!positiveInteger(record[field], true)) errors[field] = "Enter a positive number of days.";
    }
    if (positiveInteger(record.estimatedDaysMin, true) && positiveInteger(record.estimatedDaysMax, true)
      && record.estimatedDaysMin !== "" && record.estimatedDaysMax !== ""
      && Number(record.estimatedDaysMax) < Number(record.estimatedDaysMin)) {
      errors.estimatedDaysMax = "Maximum delivery days must be at least the minimum.";
    }
  } else if (kind === "size") {
    requireText("code", "a size code");
    requireText("name", "a size name");
    for (const field of ["widthMm", "heightMm"]) {
      if (!validAmount(record[field]) || Number(record[field]) <= 0) {
        errors[field] = "Enter a positive dimension in millimetres.";
      }
    }
  } else if (kind === "cover" || kind === "paper") {
    requireText("name", `a ${kind} name`);
    if (kind === "paper" && !positiveInteger(record.weightGsm, true)) {
      errors.weightGsm = "Enter a positive paper weight in gsm.";
    }
  } else if (kind === "variant") {
    requireText("sku", "a variant SKU");
    for (const field of ["productId", "sizeId", "coverTypeId", "paperTypeId"]) {
      if (!record[field]) errors[field] = "Choose an option.";
    }
    amount("basePrice", "variant price");
    currency();
  } else if (kind === "rule") {
    requireText("name", "a rule name");
    if (!["fixed", "percent"].includes(record.adjustmentType ?? record.type)) {
      errors.adjustmentType = "Choose a fixed or percentage adjustment.";
    }
    amount("amount", "adjustment amount");
  } else if (kind === "discount") {
    if (!["fixed", "percent"].includes(record.type)) errors.type = "Choose a fixed or percentage discount.";
    amount("value", "discount value");
    if (validAmount(record.value) && Number(record.value) <= 0) {
      errors.value = "Discount value must be greater than zero.";
    }
    if (record.type === "percent" && validAmount(record.value) && Number(record.value) > 100) {
      errors.value = "Percentage discounts cannot exceed 100.";
    }
    if (!positiveInteger(record.maximumUses, true)) {
      errors.maximumUses = "Enter a positive maximum-use count.";
    }
  } else {
    throw new Error("This pricing record type cannot be validated.");
  }
  return errors;
}
