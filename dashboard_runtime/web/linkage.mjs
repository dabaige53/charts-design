// Bubble points retain their grouping value at index 3, including after styling.
export function linkageValue(params, bubble) {
  return bubble ? (Array.isArray(params.value) ? params.value[3] : null) : params.name;
}

export function linkagePoint(point, index, categories, selected, bubble) {
  const value = point && typeof point === 'object' && 'value' in point ? point.value : point;
  return {...(point && typeof point === 'object' && !Array.isArray(point) ? point : {}),value, itemStyle: {opacity: (bubble ? value?.[3] === selected : categories[index] === selected) ? 1 : .22}};
}
