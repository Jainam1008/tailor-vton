/**
 * Loads and queries kiosk/catalogue/catalogue.json - the list of approved
 * garment images published by catalogue/review.py.
 */
const Catalogue = (() => {
  let items = [];

  const DEPARTMENT_LABELS = {
    suiting: "Suiting",
    shirting: "Shirting",
    ethnic: "Ethnic Wear",
  };

  async function load() {
    const response = await fetch("catalogue/catalogue.json", { cache: "no-store" });
    if (response.status === 404) {
      // No fabrics approved yet (catalogue/review.py hasn't published
      // anything) - a normal pre-launch state, not a fatal error.
      items = [];
      return items;
    }
    if (!response.ok) {
      throw new Error(`catalogue.json request failed: HTTP ${response.status}`);
    }
    const data = await response.json();
    const allItems = Array.isArray(data.items) ? data.items : [];
    // A style can be published but marked enabled:false in catalogue.json
    // (see config.yaml's `enabled` field) - e.g. while a known quality
    // issue is being investigated. Missing the field means enabled.
    items = allItems.filter((item) => item.enabled !== false);
    return items;
  }

  function getDepartments() {
    const seen = new Set();
    const departments = [];
    for (const item of items) {
      if (!seen.has(item.department)) {
        seen.add(item.department);
        departments.push({
          id: item.department,
          label: DEPARTMENT_LABELS[item.department] || item.department,
        });
      }
    }
    return departments;
  }

  function getStyles(department) {
    const seen = new Set();
    const styles = [];
    for (const item of items) {
      if (item.department === department && !seen.has(item.style_id)) {
        seen.add(item.style_id);
        styles.push({ id: item.style_id, name: item.style_name });
      }
    }
    return styles;
  }

  function getFabrics(department, styleId) {
    return items.filter((item) => item.department === department && item.style_id === styleId);
  }

  function isEmpty() {
    return items.length === 0;
  }

  return { load, getDepartments, getStyles, getFabrics, isEmpty };
})();
