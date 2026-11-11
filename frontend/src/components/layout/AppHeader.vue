<template>
  <header class="app-header">
    <img
      class="app-logo"
      src="/assets/branding/logo_lingzhi_bencao.png"
      alt="灵枝本草"
    />
    <nav class="app-nav" aria-label="主导航">
      <RouterLink to="/recognition" active-class="is-active">智能识别</RouterLink>
      <RouterLink to="/atlas" active-class="is-active">中药材图鉴</RouterLink>
      <RouterLink to="/history" active-class="is-active">识别历史</RouterLink>
      <RouterLink to="/analysis" active-class="is-active">模型分析</RouterLink>
    </nav>
  </header>
</template>
