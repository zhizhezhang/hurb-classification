import { createRouter, createWebHistory } from 'vue-router'
import RecognitionView from '../views/RecognitionView.vue'
import AtlasView from '../views/AtlasView.vue'
import HistoryView from '../views/HistoryView.vue'
import AnalysisView from '../views/AnalysisView.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/recognition' },
    { path: '/recognition', component: RecognitionView },
    { path: '/atlas', component: AtlasView },
    { path: '/history', component: HistoryView },
    { path: '/analysis', component: AnalysisView },
  ],
})
