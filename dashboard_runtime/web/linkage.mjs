// Bubble points retain their grouping value at index 3, including after styling.
export function linkageValue(params, bubble) {
  return bubble ? (Array.isArray(params.value) ? params.value[3] : null) : params.name;
}
