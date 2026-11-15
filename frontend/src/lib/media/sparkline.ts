/**
 * 迷你趋势线（sparkline）的坐标计算。
 *
 * 放到纯函数里是因为"少一个点 / 全部相等 / 只有一个点"这三种情况在模板里
 * 最容易出 NaN 或除以零，而 SVG 一旦写了 NaN 整条线就消失，很难查。
 */

export interface SparkPoint {
  /** ISO 日期，仅用于 tooltip */
  date: string;
  value: number;
}

export interface SparkResult {
  /** `polyline` 的 points 属性；点不足 2 个时为空串 */
  points: string;
  /** 是否有足够的数据画线 */
  ready: boolean;
  min: number;
  max: number;
}

/**
 * 生成 viewBox 内（0..width, 0..height）的折线点。
 * 数值越大越靠上（y 轴反转），单点或空序列返回 ready=false 让调用方显示占位。
 */
export function sparkPoints(
  series: readonly SparkPoint[],
  width: number,
  height: number
): SparkResult {
  if (series.length < 2 || width <= 0 || height <= 0) {
    const values = series.map((p) => p.value);
    return {
      points: '',
      ready: false,
      min: values.length ? Math.min(...values) : 0,
      max: values.length ? Math.max(...values) : 0
    };
  }

  const values = series.map((p) => p.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1; // 全相等时画一条水平线，而不是除以 0
  const stepX = width / (series.length - 1);

  const points = series
    .map((p, i) => {
      const x = i * stepX;
      // 上下各留 1px，避免线被 viewBox 裁掉
      const y = height - 1 - ((p.value - min) / span) * (height - 2);
      return `${round(x)},${round(y)}`;
    })
    .join(' ');

  return { points, ready: true, min, max };
}

function round(n: number): string {
  return (Math.round(n * 10) / 10).toString();
}

/** 首尾差值（用于"本周 +1.2GB"这类文案）；点不足 2 个返回 null。 */
export function trendDelta(series: readonly SparkPoint[]): number | null {
  if (series.length < 2) return null;
  return series[series.length - 1].value - series[0].value;
}
