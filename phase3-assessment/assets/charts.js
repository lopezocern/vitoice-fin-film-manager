(function() {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();
  var bg3 = style.getPropertyValue('--bg3').trim();
  var danger = style.getPropertyValue('--danger').trim();
  var success = style.getPropertyValue('--success').trim();

  // ============ Chart 1: 三层难度雷达图 ============
  var chartRadar = echarts.init(document.getElementById('chart-radar'), null, { renderer: 'svg' });
  chartRadar.setOption({
    animation: false,
    tooltip: { appendToBody: true },
    legend: {
      data: ['当前难度', '可接受阈值'],
      top: 0,
      textStyle: { color: muted, fontSize: 12 }
    },
    radar: {
      indicator: [
        { name: '数据层改造', max: 5 },
        { name: '服务层改造', max: 5 },
        { name: '前端层改造', max: 5 },
        { name: 'Tauri深度链接', max: 5 },
        { name: '后台任务机制', max: 5 },
        { name: 'Windows兼容', max: 5 }
      ],
      shape: 'polygon',
      splitNumber: 5,
      axisName: { color: ink, fontSize: 13, fontWeight: 600 },
      splitLine: { lineStyle: { color: rule } },
      splitArea: { areaStyle: { color: [bg2, bg3] } },
      axisLine: { lineStyle: { color: rule } }
    },
    series: [{
      type: 'radar',
      data: [
        {
          value: [3, 2, 2, 4, 3, 3],
          name: '当前难度',
          areaStyle: { color: accent + '40' },
          lineStyle: { color: accent, width: 2 },
          itemStyle: { color: accent }
        },
        {
          value: [2, 2, 2, 2, 2, 2],
          name: '可接受阈值',
          areaStyle: { color: accent2 + '20' },
          lineStyle: { color: accent2, width: 1.5, type: 'dashed' },
          itemStyle: { color: accent2 }
        }
      ]
    }]
  });
  window.addEventListener('resize', function() { chartRadar.resize(); });

  // ============ Chart 2: 三方案工作量堆叠对比 ============
  var chartStacked = echarts.init(document.getElementById('chart-stacked'), null, { renderer: 'svg' });
  chartStacked.setOption({
    animation: false,
    tooltip: {
      appendToBody: true,
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: function(params) {
        var total = 0;
        var lines = params.map(function(p) {
          total += p.value;
          return p.marker + ' ' + p.seriesName + ': ' + p.value + ' 周';
        });
        return '<b>' + params[0].name + '</b><br/>' + lines.join('<br/>') + '<br/><b>合计: ' + total + ' 周</b>';
      }
    },
    legend: {
      top: 0,
      textStyle: { color: muted, fontSize: 12 },
      type: 'scroll'
    },
    grid: { left: '3%', right: '4%', bottom: '3%', top: 60, containLabel: true },
    xAxis: {
      type: 'category',
      data: ['纯迁移适配', '纯重写', '混合策略（推荐）'],
      axisLabel: { color: ink, fontSize: 13, fontWeight: 600 },
      axisLine: { lineStyle: { color: rule } },
      axisTick: { show: false }
    },
    yAxis: {
      type: 'value',
      name: '周',
      nameTextStyle: { color: muted, fontSize: 12 },
      axisLabel: { color: muted, fontSize: 12 },
      splitLine: { lineStyle: { color: rule } }
    },
    series: [
      {
        name: '脚手架+基础设施',
        type: 'bar',
        stack: 'total',
        data: [0, 2.5, 1.5],
        itemStyle: { color: muted },
        emphasis: { itemStyle: { color: muted } }
      },
      {
        name: '数据模型+扫描',
        type: 'bar',
        stack: 'total',
        data: [1.5, 1.75, 1.75],
        itemStyle: { color: accent2 + 'aa' }
      },
      {
        name: '媒体管理基础',
        type: 'bar',
        stack: 'total',
        data: [0, 2.5, 1.25],
        itemStyle: { color: accent2 }
      },
      {
        name: '播放能力',
        type: 'bar',
        stack: 'total',
        data: [0, 2, 0.5],
        itemStyle: { color: accent + '99' }
      },
      {
        name: '第三阶段差异化',
        type: 'bar',
        stack: 'total',
        data: [5.5, 5.5, 5.5],
        itemStyle: { color: accent },
        label: {
          show: true,
          position: 'inside',
          formatter: function(p) { return p.value + 'w'; },
          color: '#fff',
          fontWeight: 700,
          fontSize: 11
        }
      },
      {
        name: '迁移+打磨',
        type: 'bar',
        stack: 'total',
        data: [0.5, 1.75, 1.25],
        itemStyle: { color: accent + '55' }
      },
      {
        name: '合计',
        type: 'bar',
        stack: '',
        data: [],
        label: {
          show: true,
          position: 'top',
          formatter: function(p) { return ''; }
        }
      }
    ]
  });
  // 添加合计 label 通过 markPoint
  chartStacked.setOption({
    series: [{
      name: '合计标注',
      type: 'bar',
      stack: 'total',
      data: [9.5, 16, 12].map(function(v, i) {
        return {
          value: 0.01,
          label: {
            show: true,
            position: 'top',
            formatter: ['9-10 周', '14-18 周', '11-13 周'][i],
            color: i === 2 ? success : (i === 1 ? danger : accent2),
            fontWeight: 700,
            fontSize: 13
          }
        };
      }),
      itemStyle: { color: 'transparent' }
    }]
  });
  window.addEventListener('resize', function() { chartStacked.resize(); });

  // ============ Chart 3: Python 性能对比 ============
  var chartPython = echarts.init(document.getElementById('chart-python'), null, { renderer: 'svg' });
  chartPython.setOption({
    animation: false,
    tooltip: { appendToBody: true, trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { top: 0, textStyle: { color: muted, fontSize: 12 } },
    grid: { left: '3%', right: '4%', bottom: '3%', top: 50, containLabel: true },
    xAxis: {
      type: 'category',
      data: ['并发用户', '数据规模(万)', '响应延迟(ms)', '批量并行度'],
      axisLabel: { color: ink, fontSize: 12 },
      axisLine: { lineStyle: { color: rule } },
      axisTick: { show: false }
    },
    yAxis: [
      {
        type: 'value',
        name: '家庭场景',
        position: 'left',
        nameTextStyle: { color: success, fontSize: 11 },
        axisLabel: { color: muted, fontSize: 11 },
        splitLine: { lineStyle: { color: rule } }
      },
      {
        type: 'value',
        name: 'Python短板触发点',
        position: 'right',
        nameTextStyle: { color: danger, fontSize: 11 },
        axisLabel: { color: muted, fontSize: 11 },
        splitLine: { show: false }
      }
    ],
    series: [
      {
        name: '家庭场景实际值',
        type: 'bar',
        data: [3, 10, 200, 4],
        itemStyle: { color: success + 'cc' },
        label: { show: true, position: 'top', color: success, fontSize: 11, fontWeight: 600 }
      },
      {
        name: 'Python短板触发点',
        type: 'bar',
        data: [10, 50, 10, 1],
        itemStyle: { color: danger + '99' },
        label: { show: true, position: 'top', color: danger, fontSize: 11, fontWeight: 600 }
      }
    ]
  });
  window.addEventListener('resize', function() { chartPython.resize(); });

  // ============ Chart 4: 1T 导入耗时拆解 ============
  var chartImport = echarts.init(document.getElementById('chart-import'), null, { renderer: 'svg' });
  chartImport.setOption({
    animation: false,
    tooltip: {
      appendToBody: true,
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: function(params) {
        return params[0].name + '<br/>' + params[0].marker + ' 耗时: ' + params[0].value + ' ' + params[0].data.unit;
      }
    },
    grid: { left: '3%', right: '8%', bottom: '3%', top: 30, containLabel: true },
    xAxis: {
      type: 'value',
      name: '耗时（秒，对数刻度）',
      nameTextStyle: { color: muted, fontSize: 11 },
      axisLabel: {
        color: muted,
        fontSize: 11,
        formatter: function(v) {
          if (v >= 60) return (v / 60).toFixed(0) + '分';
          return v + '秒';
        }
      },
      splitLine: { lineStyle: { color: rule } },
      min: 1,
      max: 3600,
      logBase: 10
    },
    yAxis: {
      type: 'category',
      data: ['扫描(os.walk+64KB)', '缩略图串行(1000个)', '缩略图并行(4线程)', '缩略图懒生成', '首次播放ffprobe'],
      axisLabel: { color: ink, fontSize: 12 },
      axisLine: { lineStyle: { color: rule } },
      axisTick: { show: false }
    },
    series: [{
      type: 'bar',
      data: [
        { value: 20, unit: '秒', itemStyle: { color: success } },
        { value: 2400, unit: '秒 (40分钟)', itemStyle: { color: danger } },
        { value: 540, unit: '秒 (9分钟)', itemStyle: { color: accent2 } },
        { value: 1, unit: '秒', itemStyle: { color: success } },
        { value: 0.8, unit: '秒/文件', itemStyle: { color: accent } }
      ],
      label: {
        show: true,
        position: 'right',
        color: ink,
        fontSize: 11,
        fontWeight: 600,
        formatter: function(p) { return p.data.unit; }
      },
      barWidth: '55%'
    }]
  });
  window.addEventListener('resize', function() { chartImport.resize(); });

})();
