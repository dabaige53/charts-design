"""Shared density controls for every generated Cartesian chart builder."""


def with_chart_interactions(builder):
    return """(() => {
      const chart = (""" + builder + """);
      const build = chart.optionBuilder;
      chart.optionBuilder = (...args) => {
        const option = build(...args);
        const zoom = option.dataZoom;
        if (zoom && (!Array.isArray(zoom) || zoom.length)) return option;
        const series = Array.isArray(option.series) ? option.series : [option.series];
        if (!series.some(item => item && ['bar', 'line'].includes(item.type))) return option;
        const lines = series.some(item => item?.type === 'line');
        const axes = key => Array.isArray(option[key]) ? option[key] : [option[key]];
        for (const [key, horizontal] of [['yAxis', true], ['xAxis', false]]) {
          const index = axes(key).findIndex(axis => axis?.type === 'category' || (!horizontal && axis?.type === 'time'));
          if (index < 0) continue;
          const axis = axes(key)[index];
          const count = axis.data?.length || Math.max(0, ...series.map(item => item?.data?.length || 0));
          const windowSize = lines ? 24 : 12;
          if (count <= windowSize) continue;
          if (Array.isArray(option.grid) && option.grid.length > 1) continue;
          const grid = Array.isArray(option.grid) ? option.grid[0] : (option.grid ||= {});
          const field = horizontal ? 'yAxisIndex' : 'xAxisIndex';
          const range = axis.type === 'time'
            ? {start: Math.max(0, 100 - (windowSize - 1) / (count - 1) * 100), end: 100}
            : {startValue: lines ? count - windowSize : 0, endValue: lines ? count - 1 : windowSize - 1, rangeMode: ['value', 'value']};
          const common = {[field]: index, ...range, filterMode: 'filter'};
          option.dataZoom = [
            {...common, type: 'inside', zoomOnMouseWheel: true, moveOnMouseWheel: false, moveOnMouseMove: true},
            {...common, type: 'slider', showDetail: false, brushSelect: false,
             ...(horizontal ? {orient: 'vertical', right: 4, top: 38, bottom: 38, width: 14} : {bottom: 4, height: 16})}
          ];
          if (horizontal) {grid.right = Math.max(Number(grid.right) || 0, 52); axis.axisLabel = {...axis.axisLabel, interval: 0, width: 160, overflow: 'truncate'};}
          else {grid.bottom = Math.max(Number(grid.bottom) || 0, 76); axis.axisLabel = {...axis.axisLabel, hideOverlap: true};}
          option.toolbox = {...option.toolbox, feature: {...option.toolbox?.feature, restore: {title: '重置缩放'}}};
          return option;
        }
        return option;
      };
      return chart;
    })()"""
