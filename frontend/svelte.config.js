import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
  preprocess: vitePreprocess(),
  kit: {
    adapter: adapter({
      fallback: 'index.html'
    }),
    // 必须固定：kit 2.70 默认 version.name=Date.now()，SPA fallback 模式下
    // html 引导脚本与客户端 runtime 的 __sveltekit_<hash> 指纹因构建时刻
    // 不同而不一致 → 启动即 TypeError: reading 'data'（白屏）。
    version: { name: '1' }
  }
};

export default config;
