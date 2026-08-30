(function() {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();

  // --- Chart: Workload Comparison ---
  var chartEl = document.getElementById('chart-workload');
  if (!chartEl) return;
  var chart = echarts.init(chartEl, null, { renderer: 'svg' });

  chart.setOption({
    animation: false,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      appendToBody: true,
      backgroundColor: bg2,
      borderColor: rule,
      textStyle: { color: ink, fontFamily: 'InstrumentSans, sans-serif' }
    },
    legend: {
      data: ['原混合策略', '更新后方案'],
      top: 0,
      right: 0,
      textStyle: { color: muted, fontSize: 12 },
      itemWidth: 14,
      itemHeight: 10
    },
    grid: { left: '8%', right: '5%', bottom: '8%', top: '18%', containLabel: true },
    xAxis: {
      type: 'category',
      data: ['数据层', '服务层', '无状态工具', '前端', '总计'],
      axisLine: { lineStyle: { color: rule } },
      axisLabel: { color: muted, fontSize: 12, fontFamily: 'InstrumentSans, sans-serif' },
      axisTick: { show: false }
    },
    yAxis: {
      type: 'value',
      name: '周',
      nameTextStyle: { color: muted, fontSize: 11 },
      axisLine: { show: false },
      axisLabel: { color: muted, fontSize: 11 },
      splitLine: { lineStyle: { color: rule, type: 'dashed', opacity: 0.5 } }
    },
    series: [
      {
        name: '原混合策略',
        type: 'bar',
        data: [2.5, 4, 1, 2.5, 10],
        itemStyle: {
          color: accent2,
          borderRadius: [4, 4, 0, 0]
        },
        barWidth: '28%',
        label: {
          show: true,
          position: 'top',
          color: muted,
          fontSize: 11,
          fontFamily: 'JetBrainsMono, monospace',
          formatter: '{c}w'
        }
      },
      {
        name: '更新后方案',
        type: 'bar',
        data: [1.5, 4, 1, 5.5, 12],
        itemStyle: {
          color: accent,
          borderRadius: [4, 4, 0, 0]
        },
        barWidth: '28%',
        label: {
          show: true,
          position: 'top',
          color: ink,
          fontSize: 11,
          fontFamily: 'JetBrainsMono, monospace',
          fontWeight: 600,
          formatter: '{c}w'
        }
      }
    ]
  });

  window.addEventListener('resize', function() { chart.resize(); });
})();
