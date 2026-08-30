(function() {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var ink2 = style.getPropertyValue('--ink2').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();
  var danger = style.getPropertyValue('--danger').trim();
  var ok = style.getPropertyValue('--ok').trim();

  var axisLabel = { color: muted, fontSize: 12 };
  var axisLine = { lineStyle: { color: rule } };
  var splitLine = { lineStyle: { color: rule, type: 'dashed' } };

  // ---- 图表1：组件文件行数对比 ----
  var chart1 = echarts.init(document.getElementById('chart-component-size'), null, { renderer: 'svg' });
  chart1.setOption({
    animation: false,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: bg2,
      borderColor: rule,
      textStyle: { color: ink, fontSize: 12 },
      appendToBody: true
    },
    legend: {
      data: ['当前行数', '建议拆分后'],
      textStyle: { color: ink2, fontSize: 12 },
      top: 8
    },
    grid: { left: 130, right: 30, top: 50, bottom: 30 },
    xAxis: {
      type: 'value',
      max: 2600,
      axisLabel: axisLabel,
      axisLine: axisLine,
      splitLine: splitLine
    },
    yAxis: {
      type: 'category',
      data: ['detail 页', 'Sidebar', 'manage 页', 'player 页', 'media 页'],
      axisLabel: { color: ink2, fontSize: 12 },
      axisLine: axisLine,
      axisTick: { show: false }
    },
    series: [
      {
        name: '当前行数',
        type: 'bar',
        data: [2472, 1738, 1735, 2025, 1016],
        itemStyle: {
          color: accent,
          borderRadius: [0, 4, 4, 0]
        },
        barWidth: 14,
        label: {
          show: true,
          position: 'right',
          color: ink2,
          fontSize: 11,
          formatter: '{c} 行'
        }
      },
      {
        name: '建议拆分后',
        type: 'bar',
        data: [400, 350, 300, 500, 500],
        itemStyle: {
          color: accent2,
          borderRadius: [0, 4, 4, 0]
        },
        barWidth: 14,
        label: {
          show: true,
          position: 'right',
          color: muted,
          fontSize: 11,
          formatter: '~{c} 行'
        }
      }
    ]
  });
  window.addEventListener('resize', function() { chart1.resize(); });

  // ---- 图表2：优先级分布饼图 ----
  var chart2 = echarts.init(document.getElementById('chart-priority-pie'), null, { renderer: 'svg' });
  chart2.setOption({
    animation: false,
    tooltip: {
      trigger: 'item',
      backgroundColor: bg2,
      borderColor: rule,
      textStyle: { color: ink, fontSize: 12 },
      appendToBody: true,
      formatter: '{b}: {c} 项 ({d}%)'
    },
    legend: {
      orient: 'vertical',
      right: 20,
      top: 'center',
      textStyle: { color: ink2, fontSize: 12 },
      itemWidth: 12,
      itemHeight: 12
    },
    series: [{
      type: 'pie',
      radius: ['40%', '68%'],
      center: ['38%', '50%'],
      avoidLabelOverlap: false,
      itemStyle: {
        borderColor: bg2,
        borderWidth: 2
      },
      label: {
        show: true,
        color: ink,
        fontSize: 13,
        fontWeight: 600,
        formatter: '{c}'
      },
      labelLine: { show: false },
      data: [
        { value: 2, name: 'P0 即时修复', itemStyle: { color: danger } },
        { value: 6, name: 'P1 架构重构', itemStyle: { color: accent } },
        { value: 5, name: 'P2 体验深化', itemStyle: { color: accent2 } },
        { value: 5, name: 'P3 产品打磨', itemStyle: { color: muted } }
      ]
    }]
  });
  window.addEventListener('resize', function() { chart2.resize(); });

  // ---- 图表3：各维度改进项数量对比 ----
  var chart3 = echarts.init(document.getElementById('chart-dimension-bar'), null, { renderer: 'svg' });
  chart3.setOption({
    animation: false,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: bg2,
      borderColor: rule,
      textStyle: { color: ink, fontSize: 12 },
      appendToBody: true
    },
    legend: {
      data: ['已完成', '待执行'],
      textStyle: { color: ink2, fontSize: 12 },
      top: 8
    },
    grid: { left: 80, right: 30, top: 50, bottom: 30 },
    xAxis: {
      type: 'value',
      axisLabel: axisLabel,
      axisLine: axisLine,
      splitLine: splitLine
    },
    yAxis: {
      type: 'category',
      data: ['后端 / API', '前端架构', '产品设计'],
      axisLabel: { color: ink2, fontSize: 12 },
      axisLine: axisLine,
      axisTick: { show: false }
    },
    series: [
      {
        name: '已完成',
        type: 'bar',
        data: [6, 1, 0],
        itemStyle: {
          color: ok,
          borderRadius: [0, 4, 4, 0]
        },
        barWidth: 18,
        label: {
          show: true,
          position: 'right',
          color: ink2,
          fontSize: 11
        }
      },
      {
        name: '待执行',
        type: 'bar',
        data: [5, 9, 4],
        itemStyle: {
          color: accent,
          borderRadius: [0, 4, 4, 0]
        },
        barWidth: 18,
        label: {
          show: true,
          position: 'right',
          color: ink2,
          fontSize: 11
        }
      }
    ]
  });
  window.addEventListener('resize', function() { chart3.resize(); });
})();
